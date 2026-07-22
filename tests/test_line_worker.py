"""WO-002 Worker body 測試（真 PostgreSQL test DB + mock LLM/LINE provider）。

覆蓋 8 場景：pre-filter、LLM 失敗降級、fail-closed（信心/無店/無 owner）、
建單寫 DB（customer_id + 單價 0 無 ×100）、去重（同 webhookEventId 只一單）、多 event。
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult
from app.models import Customer, Order, OrderItem, Plan, Store, User
from app.workers import line_worker


# ── 測試替身 ────────────────────────────────────────────────────────────────
class _FakeLLM:
    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    async def extract_order(self, text=None, image_url=None, industry_type="ecom"):
        if self.exc:
            raise self.exc
        return self.result


class _FakeNotif:
    def __init__(self):
        self.sent = []

    async def send_message(self, to, text, reply_token=None):
        self.sent.append({"to": to, "text": text, "reply_token": reply_token})


def _install(monkeypatch, llm, notif, store_id):
    monkeypatch.setattr("app.providers.get_llm_provider", lambda: llm)
    monkeypatch.setattr("app.providers.get_notification_provider", lambda: notif)
    monkeypatch.setattr(line_worker.settings, "default_store_id", store_id)


# ── seed / payload / run helpers ─────────────────────────────────────────────
def _seed(db, *, owner_role="owner"):
    plan = Plan(name="lite", monthly_price=0)
    db.add(plan)
    db.flush()
    store = Store(name="乖乖商店", industry_type="ecom", market="tw")
    db.add(store)
    db.flush()
    user = User(line_id="Uowner", name="老闆", role=owner_role,
                store_id=store.id, plan_id=plan.id)
    db.add(user)
    db.flush()
    db.commit()
    return store, user


def _ok_result(name="王小明"):
    # v0：AI 只抽 品項+數量+客戶，unit_price 留 0（不自動算價）
    return ExtractionResult(
        items=[ExtractedItem(product_name="蘋果", quantity=3, unit_price=0)],
        customer_name=name, confidence_score=0.9, industry_type="ecom",
        raw={"src": "test"},
    )


def _text_payload(event_id="evt-1", uid="Ubuyer001", text="蘋果 x3"):
    return {"destination": "Ubot", "events": [{
        "type": "message", "webhookEventId": event_id, "replyToken": "rt-" + event_id,
        "source": {"type": "user", "userId": uid},
        "message": {"type": "text", "text": text},
    }]}


def _run(payload, db):
    asyncio.run(line_worker.process_webhook_event(payload, db=db))


def _order_count(db):
    return db.execute(select(func.count(Order.id))).scalar_one()


# ── 場景 1：非文字 event → pre-filter，不建單 ───────────────────────────────
def test_non_text_event_no_order(db_session, monkeypatch):
    store, _ = _seed(db_session)
    notif = _FakeNotif()
    _install(monkeypatch, _FakeLLM(result=_ok_result()), notif, store.id)
    payload = {"destination": "Ubot", "events": [{
        "type": "message", "webhookEventId": "e1", "replyToken": "rt",
        "source": {"userId": "Ub"}, "message": {"type": "image"}}]}
    _run(payload, db_session)
    assert _order_count(db_session) == 0


# ── 場景 2：LLM 例外 → 降級通知，不建單 ─────────────────────────────────────
def test_llm_failure_notifies_and_no_order(db_session, monkeypatch):
    store, _ = _seed(db_session)
    notif = _FakeNotif()
    _install(monkeypatch, _FakeLLM(exc=RuntimeError("boom")), notif, store.id)
    _run(_text_payload(), db_session)
    assert _order_count(db_session) == 0
    assert notif.sent and "稍後再試" in notif.sent[0]["text"]


# ── 場景 3：信心 < 閾值 → fail-closed，不建單 ───────────────────────────────
def test_low_confidence_fail_closed(db_session, monkeypatch):
    store, _ = _seed(db_session)
    res = ExtractionResult(items=[ExtractedItem(product_name="蘋果", quantity=3)],
                           confidence_score=0.3, industry_type="ecom")
    notif = _FakeNotif()
    _install(monkeypatch, _FakeLLM(result=res), notif, store.id)
    _run(_text_payload(), db_session)
    assert _order_count(db_session) == 0
    assert notif.sent and "無法解析" in notif.sent[0]["text"]


# ── 場景 4：信心足 → 建單寫 DB（customer_id + 單價 0，無 ×100）───────────────
def test_high_confidence_creates_order(db_session, monkeypatch):
    store, owner = _seed(db_session)
    notif = _FakeNotif()
    _install(monkeypatch, _FakeLLM(result=_ok_result()), notif, store.id)
    _run(_text_payload(event_id="evt-x", uid="Ubuyer9"), db_session)

    orders = db_session.execute(select(Order)).scalars().all()
    assert len(orders) == 1
    o = orders[0]
    assert o.store_id == store.id
    assert o.user_id == owner.id            # owner 反查
    assert o.customer_id is not None        # 綁客戶
    assert o.line_event_id == "evt-x"       # 去重鍵寫入
    assert o.status == "pending_confirm"
    assert o.total_cents == 0               # v0 不自動算價
    assert o.channel == "line"

    items = db_session.execute(select(OrderItem)).scalars().all()
    assert len(items) == 1
    assert items[0].product_name == "蘋果" and items[0].quantity == 3
    assert items[0].unit_price_cents == 0 and items[0].subtotal_cents == 0  # ⛔ 無 ×100

    cust = db_session.get(Customer, o.customer_id)
    assert cust.line_user_id == "Ubuyer9" and cust.store_id == store.id
    assert notif.sent and "已收到您的訂單" in notif.sent[0]["text"]


# ── 場景 5：同 webhookEventId 兩次 → 只一單（UNIQUE 去重）────────────────────
def test_duplicate_event_creates_one_order(db_session, monkeypatch):
    store, _ = _seed(db_session)
    _install(monkeypatch, _FakeLLM(result=_ok_result()), _FakeNotif(), store.id)
    p = _text_payload(event_id="dup-1", uid="Ubuyer")
    _run(p, db_session)
    _run(p, db_session)   # 重放同一 event
    assert _order_count(db_session) == 1


# ── 場景 6：store 不存在 → fail-closed，不建孤兒單 ──────────────────────────
def test_store_not_found_no_order(db_session, monkeypatch):
    _install(monkeypatch, _FakeLLM(result=_ok_result()), _FakeNotif(), 999)
    _run(_text_payload(), db_session)
    assert _order_count(db_session) == 0


# ── 場景 7：store 有但無 owner → fail-closed ────────────────────────────────
def test_owner_not_found_no_order(db_session, monkeypatch):
    store, _ = _seed(db_session, owner_role="staff")   # 有 user 但非 owner
    _install(monkeypatch, _FakeLLM(result=_ok_result()), _FakeNotif(), store.id)
    _run(_text_payload(), db_session)
    assert _order_count(db_session) == 0


# ── 場景 8：一 payload 多 event → 各自建單，同買家只一 customer ──────────────
def test_multi_events_two_orders_one_customer(db_session, monkeypatch):
    store, _ = _seed(db_session)
    _install(monkeypatch, _FakeLLM(result=_ok_result()), _FakeNotif(), store.id)
    payload = {"destination": "Ubot", "events": [
        {"type": "message", "webhookEventId": "m1", "replyToken": "r1",
         "source": {"userId": "UsameBuyer"}, "message": {"type": "text", "text": "蘋果 x3"}},
        {"type": "message", "webhookEventId": "m2", "replyToken": "r2",
         "source": {"userId": "UsameBuyer"}, "message": {"type": "text", "text": "香蕉 x2"}},
    ]}
    _run(payload, db_session)
    assert _order_count(db_session) == 2
    assert db_session.execute(select(func.count(Customer.id))).scalar_one() == 1
