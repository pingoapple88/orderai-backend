"""訂單服務（律三：store_id 隔離；律四：audit）。金額全程整數分，顯示層才 /100。"""
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models import AuditLog, Order, OrderItem
from app.services.tax import compute_tax

# API 契約 v1.0：status 列舉僅此五個
ORDER_STATUSES = {
    "pending_confirm", "confirmed", "cancelled", "completed", "needs_review",
}


def _audit(db: Session, principal: dict, action: str, resource_id: Optional[int],
           old=None, new=None) -> None:
    # audit_logs 已對齊 store_id（0004 全面改名）。
    db.add(AuditLog(
        user_id=principal.get("user_id"),
        store_id=principal.get("store_id"),
        action=action, resource_type="order", resource_id=resource_id,
        old_value=old, new_value=new,
    ))


def _order_number(db: Session) -> str:
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y%m%d")
    cnt = db.execute(
        select(func.count(Order.id)).where(Order.order_number.like(f"OA-{date_part}-%"))
    ).scalar_one()
    return f"OA-{date_part}-{cnt + 1:04d}"


def create_order(db: Session, principal: dict, data: dict) -> Order:
    """由 worker / 測試建單。金額整數分：unit_price 直接是分。"""
    items = data.get("items", [])
    subtotal_sum = sum(int(i["quantity"]) * int(i["unit_price"]) for i in items)  # 整數分
    market = data.get("market", "tw")
    tax = compute_tax(subtotal_sum, market)          # 情境三：一次性計稅（整數分）
    total = subtotal_sum + tax

    order = Order(
        user_id=principal["user_id"],
        store_id=principal.get("store_id"),
        order_number=_order_number(db),
        customer_name=data.get("customer_name"),
        customer_phone=data.get("customer_phone"),
        customer_email=data.get("customer_email"),
        total_cents=total,
        currency=data.get("currency", "TWD"),
        status="pending_confirm",
        channel=data.get("channel"),
        notes=data.get("notes"),
    )
    db.add(order)
    db.flush()
    for i in items:
        q, up = int(i["quantity"]), int(i["unit_price"])  # up 為整數分
        db.add(OrderItem(
            order_id=order.id, product_name=i.get("product_name"),
            quantity=q, unit=i.get("unit", "個"),
            unit_price_cents=up, subtotal_cents=q * up,
        ))
    _audit(db, principal, "order.create", order.id, new={"total_cents": total, "tax_cents": tax})
    db.commit()
    db.refresh(order)
    event_bus.publish("order.created", {"order_id": order.id, "store_id": order.store_id})
    return order


def list_orders(db: Session, store_id: int, *, page=1, limit=20, status=None):
    where = [Order.store_id == store_id]                       # 租戶隔離：WHERE store_id
    if status:
        where.append(Order.status == status)
    total = db.execute(select(func.count(Order.id)).where(*where)).scalar_one()
    rows = db.execute(
        select(Order).where(*where).order_by(Order.created_at.desc())
        .limit(limit).offset((page - 1) * limit)
    ).scalars().all()
    return rows, total


def get_order(db: Session, store_id: int, order_id: int) -> Optional[Order]:
    return db.execute(
        select(Order).where(Order.id == order_id, Order.store_id == store_id)
    ).scalar_one_or_none()


def update_order(db: Session, principal: dict, store_id: int, order_id: int,
                 updates: dict) -> Optional[Order]:
    """修正 AI 抄單結果。可改客戶欄位 / status / notes / items（重算金額，整數分）。"""
    order = get_order(db, store_id, order_id)
    if not order:
        return None
    old = {"status": order.status, "total_cents": order.total_cents}

    for f in ("customer_name", "customer_phone", "customer_email", "notes"):
        if updates.get(f) is not None:
            setattr(order, f, updates[f])

    if updates.get("status") is not None:
        if updates["status"] not in ORDER_STATUSES:
            raise ValueError(f"invalid status: {updates['status']}")
        order.status = updates["status"]

    if updates.get("items") is not None:
        order.items.clear()
        db.flush()
        subtotal_sum = 0
        for i in updates["items"]:
            q, up = int(i["quantity"]), int(i["unit_price"])
            subtotal_sum += q * up
            order.items.append(OrderItem(
                product_name=i.get("product_name"), quantity=q,
                unit=i.get("unit", "個"), unit_price_cents=up, subtotal_cents=q * up,
            ))
        tax = compute_tax(subtotal_sum, updates.get("market", "tw"))
        order.total_cents = subtotal_sum + tax

    _audit(db, principal, "order.update", order.id, old=old,
           new={"status": order.status, "total_cents": order.total_cents})
    db.commit()
    db.refresh(order)
    event_bus.publish("order.updated", {"order_id": order.id, "store_id": order.store_id})
    return order


def confirm_order(db: Session, principal: dict, store_id: int, order_id: int) -> Optional[Order]:
    """確認 AI 抄單結果：status → confirmed，寫 confirmed_at。"""
    order = get_order(db, store_id, order_id)
    if not order:
        return None
    old = {"status": order.status}
    order.status = "confirmed"
    order.confirmed_at = datetime.now(timezone.utc)
    _audit(db, principal, "order.confirm", order.id, old=old, new={"status": "confirmed"})
    db.commit()
    db.refresh(order)
    event_bus.publish("order.confirmed", {"order_id": order.id, "store_id": order.store_id})
    return order
