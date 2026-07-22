"""WO-009 開團批次 + 貼上抄單 + 統計測試。

涵蓋派工單 §4.1 的 9 個必測 case：
  parse 不寫庫 / 重複 commit 409 / 缺價 422 回 lineNo / commit 全回滾 /
  跨店 batch 403 / A 店 parse 不得命中 B 店商品 / closed parse 409 /
  一行多品項拆分 / summary 加總 = 各 item subtotal 總和。
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult
from app.core.security import create_access_token
from app.main import app
from app.models import (AuditLog, Order, OrderBatch, OrderCommit, OrderItem,
                        Plan, Product, Store, User)
from app.services import batch_service

_MARK = "WO009_TEST"
_LINE = "Uwo009_owner"
_ctx: dict = {}


class FakeLLM:
    """確定性 LLM：依原始行文字回固定抽取結果（不呼叫真 AI）。"""
    def __init__(self, responses: dict):
        self._r = responses

    async def extract_order(self, image_url=None, text=None, industry_type="ecom"):
        if text in self._r:
            return self._r[text]
        return ExtractionResult(items=[], confidence_score=0.1, industry_type=industry_type)


def _cleanup():
    db = SessionLocal()
    try:
        sids = db.execute(select(Store.id).where(Store.name.like(f"{_MARK}%"))).scalars().all()
        if sids:
            bids = db.execute(select(OrderBatch.id).where(OrderBatch.store_id.in_(sids))).scalars().all()
            if bids:
                db.execute(delete(OrderCommit).where(OrderCommit.batch_id.in_(bids)))
            oids = db.execute(select(Order.id).where(Order.store_id.in_(sids))).scalars().all()
            if oids:
                db.execute(delete(OrderItem).where(OrderItem.order_id.in_(oids)))
                db.execute(delete(Order).where(Order.id.in_(oids)))
            db.execute(delete(OrderBatch).where(OrderBatch.store_id.in_(sids)))
            db.execute(delete(AuditLog).where(AuditLog.store_id.in_(sids)))
            db.execute(delete(Product).where(Product.store_id.in_(sids)))
            db.execute(delete(User).where(User.store_id.in_(sids)))
            db.execute(delete(Store).where(Store.id.in_(sids)))
        db.execute(delete(User).where(User.line_id == _LINE))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def env():
    """A/B 兩店 + A owner。A 有 高麗菜(4500)/地瓜(3000)；B 有 雞蛋(6000)。"""
    _cleanup()
    db = SessionLocal()
    try:
        plan_id = db.execute(select(Plan.id).order_by(Plan.id)).scalars().first()
        a = Store(name=f"{_MARK}_A", market="tw"); b = Store(name=f"{_MARK}_B", market="tw")
        db.add_all([a, b]); db.flush()
        owner = User(line_id=_LINE, name="owner", plan_id=plan_id, store_id=a.id, role="owner")
        db.add(owner)
        db.add_all([
            Product(store_id=a.id, name="高麗菜", aliases=["包心菜"], unit="顆", price_cents=4500, is_active=True),
            Product(store_id=a.id, name="地瓜", aliases=[], unit="斤", price_cents=3000, is_active=True),
            Product(store_id=b.id, name="雞蛋", aliases=[], unit="盒", price_cents=6000, is_active=True),
        ])
        db.flush()
        _ctx["user_id"] = owner.id
        ids = (a.id, b.id)
        db.commit()
    finally:
        db.close()
    yield ids
    _cleanup()


def _tok(store_id, user_id=None):
    t = create_access_token({"user_id": user_id or _ctx.get("user_id", 1),
                             "store_id": store_id, "role": "owner"})
    return {"Authorization": f"Bearer {t}"}


def _new_batch(store_id, title="0720 週日團"):
    db = SessionLocal()
    try:
        b = OrderBatch(store_id=store_id, title=title, status="open")
        db.add(b); db.commit(); db.refresh(b)
        return b.id
    finally:
        db.close()


# ── case 1：parse 不得寫庫 ────────────────────────────────────────────────────

def test_case1_parse_does_not_write_orders(env):
    store_a, _ = env
    batch_id = _new_batch(store_a)
    db = SessionLocal()
    before = db.execute(select(func.count(Order.id))).scalar_one(); db.close()

    fake = FakeLLM({"陳太太 高麗菜2顆": ExtractionResult(
        items=[ExtractedItem(product_name="高麗菜", quantity=2)],
        customer_name="陳太太", confidence_score=0.96)})
    client = TestClient(app)
    with patch("app.api.v1.batches.get_llm_provider", return_value=fake):
        r = client.post(f"/api/v1/stores/{store_a}/batches/{batch_id}/parse",
                        headers=_tok(store_a), json={"rawText": "陳太太 高麗菜2顆"})
    assert r.status_code == 200, r.text
    db = SessionLocal()
    after = db.execute(select(func.count(Order.id))).scalar_one(); db.close()
    assert after == before, "parse 不得寫入任何 order"
    assert len(r.json()["data"]["lines"]) == 1


# ── case 7：closed 批次 parse → 409 ───────────────────────────────────────────

def test_case7_parse_closed_batch_409(env):
    store_a, _ = env
    batch_id = _new_batch(store_a)
    db = SessionLocal()
    b = db.get(OrderBatch, batch_id); b.status = "closed"; db.commit(); db.close()
    fake = FakeLLM({})
    client = TestClient(app)
    with patch("app.api.v1.batches.get_llm_provider", return_value=fake):
        r = client.post(f"/api/v1/stores/{store_a}/batches/{batch_id}/parse",
                        headers=_tok(store_a), json={"rawText": "任何"})
    assert r.status_code == 409, r.text


# ── case 8：一行多品項拆成多筆 line ──────────────────────────────────────────

def test_case8_multi_item_line_split(env):
    store_a, _ = env
    batch_id = _new_batch(store_a)
    line = "王小姐 雞蛋一盒 還要地瓜3斤"
    fake = FakeLLM({line: ExtractionResult(
        items=[ExtractedItem(product_name="雞蛋", quantity=1),
               ExtractedItem(product_name="地瓜", quantity=3)],
        customer_name="王小姐", confidence_score=0.9)})
    client = TestClient(app)
    with patch("app.api.v1.batches.get_llm_provider", return_value=fake):
        r = client.post(f"/api/v1/stores/{store_a}/batches/{batch_id}/parse",
                        headers=_tok(store_a), json={"rawText": line})
    lines = r.json()["data"]["lines"]
    assert len(lines) == 2
    assert lines[0]["lineNo"] == "1" and lines[1]["lineNo"] == "1.1"
    # case 6 附帶驗證：雞蛋只在 B 店 → A 店 parse 不得命中
    egg = next(l for l in lines if l["productName"] == "雞蛋")
    assert egg["matchedProductId"] is None
    yam = next(l for l in lines if l["productName"] == "地瓜")
    assert yam["matchedProductId"] is not None and yam["unitPriceCents"] == 3000


# ── case 6：A 店 parse 不得命中 B 店商品（獨立明證）─────────────────────────

def test_case6_parse_cannot_match_other_store(env):
    store_a, _ = env
    batch_id = _new_batch(store_a)
    line = "李媽 雞蛋2盒"
    fake = FakeLLM({line: ExtractionResult(
        items=[ExtractedItem(product_name="雞蛋", quantity=2)],
        customer_name="李媽", confidence_score=0.95)})
    client = TestClient(app)
    with patch("app.api.v1.batches.get_llm_provider", return_value=fake):
        r = client.post(f"/api/v1/stores/{store_a}/batches/{batch_id}/parse",
                        headers=_tok(store_a), json={"rawText": line})
    line0 = r.json()["data"]["lines"][0]
    assert line0["matchedProductId"] is None      # 雞蛋屬 B 店
    assert line0["unitPriceCents"] is None
    assert line0["needsReview"] is True           # 未命中 → 需複核


# ── case 5：跨店讀 batch → 403（path store 不符）；本店查他店 batch → 404 ─────

def test_case5_cross_store_batch(env):
    store_a, store_b = env
    b_batch = _new_batch(store_b)
    client = TestClient(app)
    # A 的 JWT 打 /stores/B/... → verify_store_access 403
    r403 = client.get(f"/api/v1/stores/{store_b}/batches", headers=_tok(store_a))
    assert r403.status_code == 403, r403.text
    # A 的 JWT 打自己 /stores/A/batches/{B 的 batch_id} → 本店查無 → 404
    r404 = client.get(f"/api/v1/stores/{store_a}/batches/{b_batch}/summary", headers=_tok(store_a))
    assert r404.status_code == 404, r404.text


# ── case 2/3/4/9：commit + summary（不需 LLM）─────────────────────────────────

def _commit_lines():
    return [
        {"lineNo": "1", "customerName": "陳太太", "productName": "高麗菜", "qty": 2, "unitPriceCents": 4500},
        {"lineNo": "2", "customerName": "王小姐", "productName": "地瓜", "qty": 3, "unitPriceCents": 3000},
    ]


def test_case2_duplicate_commit_409(env):
    store_a, _ = env
    batch_id = _new_batch(store_a)
    client = TestClient(app)
    body = {"rawText": "陳太太 高麗菜2顆\n王小姐 地瓜3斤", "lines": _commit_lines()}
    r1 = client.post(f"/api/v1/stores/{store_a}/batches/{batch_id}/commit", headers=_tok(store_a), json=body)
    assert r1.status_code == 201, r1.text
    r2 = client.post(f"/api/v1/stores/{store_a}/batches/{batch_id}/commit", headers=_tok(store_a), json=body)
    assert r2.status_code == 409, r2.text


def test_case3_missing_price_422_with_line_no(env):
    store_a, _ = env
    batch_id = _new_batch(store_a)
    client = TestClient(app)
    lines = [
        {"lineNo": "1", "customerName": "陳太太", "productName": "高麗菜", "qty": 2, "unitPriceCents": 4500},
        {"lineNo": "2", "customerName": "王小姐", "productName": "火龍果", "qty": 1, "unitPriceCents": None},
    ]
    r = client.post(f"/api/v1/stores/{store_a}/batches/{batch_id}/commit",
                    headers=_tok(store_a), json={"rawText": "x", "lines": lines})
    assert r.status_code == 422, r.text
    detail = r.json()["error"]["message"]
    assert "2" in str(detail.get("lineNos") if isinstance(detail, dict) else detail)


def test_case4_commit_rollback_leaves_zero(env):
    """commit 中途失敗 → 全回滾，零筆殘留（service 層直測）。"""
    store_a, _ = env
    batch_id = _new_batch(store_a)
    db = SessionLocal()
    try:
        batch = db.get(OrderBatch, batch_id)
        principal = {"user_id": _ctx["user_id"], "store_id": store_a}
        bad_lines = [
            {"lineNo": "1", "customerName": "陳太太", "productName": "高麗菜", "qty": 2, "unitPriceCents": 4500},
            {"lineNo": "2", "customerName": "王小姐", "productName": "地瓜", "qty": None, "unitPriceCents": 3000},
        ]
        with pytest.raises(Exception):
            batch_service.commit_batch(db, principal, store_a, batch, "rollback-test", bad_lines)
        db.rollback()
        # 零殘留：該 batch 無 order、無 commit 記錄
        n_orders = db.execute(select(func.count(Order.id)).where(Order.batch_id == batch_id)).scalar_one()
        n_commits = db.execute(select(func.count(OrderCommit.id)).where(OrderCommit.batch_id == batch_id)).scalar_one()
        assert n_orders == 0 and n_commits == 0
    finally:
        db.close()


def test_case9_summary_totals_match_item_subtotals(env):
    store_a, _ = env
    batch_id = _new_batch(store_a)
    client = TestClient(app)
    body = {"rawText": "陳太太 高麗菜2顆\n王小姐 地瓜3斤", "lines": _commit_lines()}
    assert client.post(f"/api/v1/stores/{store_a}/batches/{batch_id}/commit",
                       headers=_tok(store_a), json=body).status_code == 201
    s = client.get(f"/api/v1/stores/{store_a}/batches/{batch_id}/summary", headers=_tok(store_a)).json()["data"]
    # summary 加總 = 各 item subtotal 總和
    item_sum = sum(it["subtotalCents"] for c in s["byCustomer"] for it in c["items"])
    assert s["totalCents"] == item_sum == (2 * 4500 + 3 * 3000)
    assert s["orderCount"] == 2
    # byProduct 依 totalQty 降序（地瓜3 > 高麗菜2）
    assert s["byProduct"][0]["productName"] == "地瓜"
    # byCustomer 依 subtotalCents 降序（高麗菜9000 > 地瓜9000？相等時序穩定即可）
    assert s["byCustomer"][0]["subtotalCents"] >= s["byCustomer"][-1]["subtotalCents"]
