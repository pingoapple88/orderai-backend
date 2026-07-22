"""開團批次 + 貼上抄單 + 統計（WO-009）。律三：全程 store_id 隔離；律七：金額整數分。

紅線：parse 與 commit 分離。parse 只回草稿、不寫任何 orders/order_items；
      commit 才在單一 transaction 內建單，任一失敗全回滾。
"""
import hashlib
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditLog, Order, OrderBatch, OrderCommit, OrderItem
from app.services import product_service

_REVIEW_CONFIDENCE = 0.85


class BatchClosed(Exception):
    """對 closed 批次 parse/commit → 409。"""


class DuplicateCommit(Exception):
    """同批次同原文重複 commit → 409。"""


class PriceRequired(Exception):
    """commit 時有 line 缺價 → 422，帶出缺價的 line_no。"""
    def __init__(self, line_nos: list):
        self.line_nos = line_nos
        super().__init__(f"price required for lines: {line_nos}")


def _audit(db: Session, principal: dict, action: str, resource_id: Optional[int], new=None) -> None:
    db.add(AuditLog(
        user_id=principal.get("user_id"), store_id=principal.get("store_id"),
        action=action, resource_type="batch", resource_id=resource_id, new_value=new,
    ))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── 批次 CRUD ─────────────────────────────────────────────────────────────────

def create_batch(db: Session, principal: dict, store_id: int, title: str) -> OrderBatch:
    b = OrderBatch(store_id=store_id, title=title, status="open")
    db.add(b)
    db.flush()
    _audit(db, principal, "batch.create", b.id, new={"title": title})
    db.commit()
    db.refresh(b)
    return b


def list_batches(db: Session, store_id: int, *, status: Optional[str] = None):
    where = [OrderBatch.store_id == store_id]                 # 律三
    if status:
        where.append(OrderBatch.status == status)
    return db.execute(
        select(OrderBatch).where(*where).order_by(OrderBatch.created_at.desc())
    ).scalars().all()


def get_batch(db: Session, store_id: int, batch_id: int) -> Optional[OrderBatch]:
    return db.execute(
        select(OrderBatch).where(OrderBatch.id == batch_id, OrderBatch.store_id == store_id)
    ).scalar_one_or_none()


def close_batch(db: Session, principal: dict, store_id: int, batch_id: int) -> Optional[OrderBatch]:
    b = get_batch(db, store_id, batch_id)
    if not b:
        return None
    if b.status == "closed":
        raise DuplicateCommit("BATCH_ALREADY_CLOSED")  # 由路由轉 409（沿用泛用 CONFLICT）
    b.status = "closed"
    b.closed_at = func.now()
    _audit(db, principal, "batch.close", b.id, new={"status": "closed"})
    db.commit()
    db.refresh(b)
    return b


# ── parse（只回草稿，⛔ 不寫庫）───────────────────────────────────────────────

async def parse_batch(db: Session, store_id: int, batch: OrderBatch, raw_text: str, llm,
                      industry_type: str = "ecom") -> dict:
    """切行 → 逐行 AI 抽取 → match_product 帶價 → 組草稿。不寫任何 orders/order_items。"""
    if batch.status == "closed":
        raise BatchClosed("BATCH_CLOSED")

    lines_out = []
    unmatched = 0
    source_lines = [ln for ln in raw_text.splitlines()]
    for idx, raw_line in enumerate(source_lines, start=1):
        if not raw_line.strip():
            continue
        result = await llm.extract_order(text=raw_line, industry_type=industry_type)
        items = result.items or []
        # 無品項（閒聊/貼圖佔位/已轉帳等）→ 不產生 line
        for j, it in enumerate(items):
            line_no = str(idx) if j == 0 else f"{idx}.{j}"
            matched = product_service.match_product(db, store_id, it.product_name)
            qty = it.quantity
            matched_id = matched.id if matched else None
            unit_price = matched.price_cents if matched else None
            needs_review = (
                result.confidence_score < _REVIEW_CONFIDENCE
                or matched_id is None
                or qty is None
            )
            if matched_id is None:
                unmatched += 1
            lines_out.append({
                "lineNo": line_no,
                "rawLine": raw_line,
                "customerName": result.customer_name,
                "productName": it.product_name,
                "qty": qty,
                "matchedProductId": matched_id,
                "unitPriceCents": unit_price,
                "confidence": round(result.confidence_score, 2),
                "needsReview": needs_review,
            })
    return {"lines": lines_out, "unmatchedCount": unmatched}


# ── commit（單一 transaction，任一失敗全回滾）────────────────────────────────

def commit_batch(db: Session, principal: dict, store_id: int, batch: OrderBatch,
                 raw_text: str, lines: list) -> dict:
    """團媽校對後寫入。sha256 去重 → 409；缺價 → 422（帶 line_no）；單一 transaction 全回滾。"""
    if batch.status == "closed":
        raise BatchClosed("BATCH_CLOSED")

    # 缺價檢查（寫入前）：任一 line unitPriceCents 為 null → 422，回出 line_no
    missing = [ln.get("lineNo") for ln in lines if ln.get("unitPriceCents") is None]
    if missing:
        raise PriceRequired(missing)

    try:
        # 去重：同批次同原文 hash 已 commit → UNIQUE 撞 → 409
        db.add(OrderCommit(batch_id=batch.id, raw_text_sha256=_sha256(raw_text)))
        db.flush()

        # 依 customerName 分組，一客一單
        by_customer: dict = {}
        for ln in lines:
            by_customer.setdefault(ln.get("customerName"), []).append(ln)

        order_count = 0
        item_count = 0
        for customer_name, cust_lines in by_customer.items():
            subtotal_sum = 0
            order = Order(
                user_id=principal["user_id"], store_id=store_id, batch_id=batch.id,
                customer_name=customer_name, status="pending_confirm",
                channel="paste", currency="TWD",
            )
            db.add(order)
            db.flush()
            for ln in cust_lines:
                qty = int(ln["qty"])                     # qty 缺 → 這裡拋錯 → 全回滾
                up = int(ln["unitPriceCents"])           # 整數分（律七）
                sub = qty * up
                subtotal_sum += sub
                db.add(OrderItem(
                    order_id=order.id, product_name=ln.get("productName"),
                    quantity=qty, unit=ln.get("unit", "個"),
                    unit_price_cents=up, subtotal_cents=sub,
                ))
                item_count += 1
            order.total_cents = subtotal_sum
            order_count += 1

        _audit(db, principal, "batch.commit", batch.id,
               new={"order_count": order_count, "item_count": item_count})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateCommit(_sha256(raw_text))
    except Exception:
        db.rollback()                                     # 任一 line 失敗 → 全回滾，零殘留
        raise

    return {"batchId": batch.id, "createdOrderCount": order_count, "createdItemCount": item_count}


# ── summary（後端聚合；前端禁止自行加總）─────────────────────────────────────

def summary(db: Session, store_id: int, batch: OrderBatch) -> dict:
    orders = db.execute(
        select(Order).where(Order.batch_id == batch.id, Order.store_id == store_id)
    ).scalars().all()

    by_customer = []
    by_product: dict = {}
    total_cents = 0
    for o in orders:
        cust_items = []
        cust_subtotal = 0
        for it in o.items:
            sub = it.subtotal_cents or 0
            cust_items.append({
                "productName": it.product_name, "qty": it.quantity,
                "unitPriceCents": it.unit_price_cents, "subtotalCents": sub,
            })
            cust_subtotal += sub
            p = by_product.setdefault(it.product_name, {"productName": it.product_name,
                                                        "totalQty": 0, "subtotalCents": 0})
            p["totalQty"] += it.quantity or 0
            p["subtotalCents"] += sub
        total_cents += cust_subtotal
        by_customer.append({
            "customerName": o.customer_name, "items": cust_items,
            "subtotalCents": cust_subtotal,
        })

    by_customer.sort(key=lambda c: c["subtotalCents"], reverse=True)
    by_product_list = sorted(by_product.values(), key=lambda p: p["totalQty"], reverse=True)

    return {
        "batch": {"id": batch.id, "title": batch.title, "status": batch.status},
        "byCustomer": by_customer,
        "byProduct": by_product_list,
        "totalCents": total_cents,
        "orderCount": len(orders),
    }
