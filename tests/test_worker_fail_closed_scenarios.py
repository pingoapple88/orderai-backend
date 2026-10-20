"""WO-04 ENG-02：抄單三情境的完整性檢查（合成資料，真 test DB）。

情境：完整訂單 → 建 pending_confirm 草稿；商品無法對應 → fail-closed 不建單 + 通知；
資料不完整（數量無效）→ fail-closed 不建單 + 通知。
失敗情境不得靜默通過（皆有通知 + 稽核）。對齊 Schema 凍結 §5.2：低信心/未通過 = fail-closed。
"""
from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult
from app.models import AuditLog, Order, Plan, Product, Store, User
from app.workers import line_worker


class _FakeLLM:
    def __init__(self, result):
        self.result = result

    async def extract_order(self, text=None, image_url=None, industry_type="ecom"):
        return self.result


class _FakeNotif:
    def __init__(self):
        self.sent = []

    async def send_message(self, to, text, reply_token=None):
        self.sent.append({"to": to, "text": text})


def _seed(db):
    plan = Plan(name="lite", channel="direct", monthly_price=0)
    db.add(plan); db.flush()
    store = Store(name="ENG02店", industry_type="ecom", market="tw")
    db.add(store); db.flush()
    owner = User(line_id="Uowner_eng02", name="老闆", role="owner",
                 store_id=store.id, plan_id=plan.id)
    apple = Product(store_id=store.id, name="蘋果", aliases=[], unit="顆", price_cents=4500)
    db.add_all([owner, apple]); db.flush(); db.commit()
    return store


def _install(monkeypatch, result, notif, store_id):
    monkeypatch.setattr("app.providers.get_llm_provider", lambda: _FakeLLM(result))
    monkeypatch.setattr("app.providers.get_notification_provider", lambda: notif)
    monkeypatch.setattr(line_worker.settings, "default_store_id", store_id)


def _payload(event_id, text):
    return {"destination": "Ubot", "events": [{
        "type": "message", "webhookEventId": event_id, "replyToken": "rt-" + event_id,
        "source": {"type": "user", "userId": "Ubuyer_eng02"},
        "message": {"type": "text", "text": text}}]}


def _run(payload, db):
    asyncio.run(line_worker.process_webhook_event(payload, db=db))


def _count(db):
    return db.execute(select(func.count(Order.id))).scalar_one()


# 情境 A：完整訂單（型錄命中、信心足、數量有效）→ 建 pending_confirm 草稿
def test_scenario_complete_creates_draft(db_session, monkeypatch):
    store = _seed(db_session)
    res = ExtractionResult(
        items=[ExtractedItem(product_name="蘋果", quantity=3, evidence="蘋果 x3", confidence_score=0.95)],
        customer_name="王小明", confidence_score=0.95, industry_type="ecom", raw={"s": 1})
    notif = _FakeNotif()
    _install(monkeypatch, res, notif, store.id)
    _run(_payload("eng02-a", "蘋果 x3"), db_session)
    orders = db_session.execute(select(Order)).scalars().all()
    assert len(orders) == 1
    assert orders[0].status == "pending_confirm"
    assert orders[0].total_cents == 13500


# 情境 B：商品無法對應（型錄未命中）→ fail-closed 不建單 + 通知
def test_scenario_unknown_product_fail_closed(db_session, monkeypatch):
    store = _seed(db_session)
    res = ExtractionResult(
        items=[ExtractedItem(product_name="不存在的商品X", quantity=1, evidence="商品X x1", confidence_score=0.95)],
        customer_name="王小明", confidence_score=0.95, industry_type="ecom", raw={"s": 1})
    notif = _FakeNotif()
    _install(monkeypatch, res, notif, store.id)
    _run(_payload("eng02-b", "商品X x1"), db_session)
    assert _count(db_session) == 0                       # 不靜默建單
    assert notif.sent and "人工確認" in notif.sent[0]["text"]   # 不靜默通過
    # 稽核留痕，含未命中原因
    dec = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai.order.decision")
    ).scalars().first()
    assert dec is not None
    assert "catalog_product_unmatched" in dec.new_value["reason_codes"]


# 情境 C：資料不完整（數量無效）→ fail-closed 不建單 + 通知
def test_scenario_incomplete_data_fail_closed(db_session, monkeypatch):
    store = _seed(db_session)
    res = ExtractionResult(
        items=[ExtractedItem(product_name="蘋果", quantity=0, evidence="蘋果", confidence_score=0.95)],
        customer_name="王小明", confidence_score=0.95, industry_type="ecom", raw={"s": 1})
    notif = _FakeNotif()
    _install(monkeypatch, res, notif, store.id)
    _run(_payload("eng02-c", "蘋果"), db_session)
    assert _count(db_session) == 0
    assert notif.sent and "人工確認" in notif.sent[0]["text"]
    dec = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai.order.decision")
    ).scalars().first()
    assert dec is not None and "invalid_quantity" in dec.new_value["reason_codes"]
