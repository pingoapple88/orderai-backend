"""WO-L3-001 對話層①：reply_composer 測試。

- 單元：事實區塊數字由程式產生、LLM 暖話不改動數字、各種失敗回退罐頭句。
- 整合（真 PostgreSQL test DB）：LLM 回覆層拋例外 → 回退罐頭句、仍送出、建單不受影響。
"""
from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult
from app.models import Order, Plan, Product, Store, User
from app.services import reply_composer as rc
from app.workers import line_worker

ITEMS = [
    rc.ReplyItem(name="蘋果", qty=3, unit_price_cents=4500),
    rc.ReplyItem(name="香蕉", qty=2, unit_price_cents=3000),
]
TOTAL = 19500
FACT_BLOCK = "蘋果 x3  $135\n香蕉 x2  $60\n總計 $195"


class _WarmLLM:
    def __init__(self, opening="哈囉，謝謝您的訂購！", closing="我們會盡快幫您準備喔！"):
        self.opening, self.closing = opening, closing
        self.calls = []

    async def compose_reply(self, outcome, brand_voice=""):
        self.calls.append({"outcome": outcome, "brand_voice": brand_voice})
        return self.opening, self.closing


class _BoomLLM:
    async def compose_reply(self, outcome, brand_voice=""):
        raise RuntimeError("llm down")


class _SlowLLM:
    async def compose_reply(self, outcome, brand_voice=""):
        await asyncio.sleep(5)
        return "慢", "慢"


def _compose(*args, **kw):
    return asyncio.run(rc.compose(*args, **kw))


# ── 事實區塊 ─────────────────────────────────────────────────────────────────
def test_fact_block_items_and_total():
    assert rc.build_fact_block(ITEMS, TOTAL) == FACT_BLOCK


def test_format_cents_non_integer_dollars():
    assert rc.format_cents(123456) == "$1,234.56"
    assert rc.format_cents(0) == "$0"


def test_warm_llm_wraps_fact_block_unchanged():
    llm = _WarmLLM()
    text = _compose(rc.OUTCOME_ORDER_CREATED, items=ITEMS, total_cents=TOTAL, llm=llm, brand_voice="俏皮")
    assert text == "哈囉，謝謝您的訂購！\n" + FACT_BLOCK + "\n我們會盡快幫您準備喔！"
    assert "總計 $195" in text and "蘋果" in text and "香蕉" in text
    assert llm.calls == [{"outcome": "order_created", "brand_voice": "俏皮"}]


def test_brand_voice_from_settings(monkeypatch):
    monkeypatch.setattr(rc.get_settings(), "reply_brand_voice", "溫柔阿姨")
    llm = _WarmLLM()
    _compose(rc.OUTCOME_ORDER_CREATED, items=ITEMS, total_cents=TOTAL, llm=llm)
    assert llm.calls[0]["brand_voice"] == "溫柔阿姨"


def test_llm_line_with_numbers_rejected_falls_back():
    # LLM 若自行寫數字（可能與事實衝突）→ 不採用，回退罐頭句；事實區塊仍正確。
    llm = _WarmLLM(opening="您買了 999 元的東西！")
    text = _compose(rc.OUTCOME_ORDER_CREATED, items=ITEMS, total_cents=TOTAL, llm=llm)
    assert "999" not in text
    assert text.startswith("已收到您的訂單：\n" + FACT_BLOCK)


# ── fail-safe ───────────────────────────────────────────────────────────────
def test_llm_exception_falls_back_to_canned_with_facts():
    text = _compose(rc.OUTCOME_ORDER_CREATED, items=ITEMS, total_cents=TOTAL, llm=_BoomLLM())
    assert text == "已收到您的訂單：\n" + FACT_BLOCK + "\n請稍候店家確認。"


def test_llm_timeout_falls_back(monkeypatch):
    monkeypatch.setattr(rc.get_settings(), "reply_llm_timeout_seconds", 0.05)
    text = _compose(rc.OUTCOME_ORDER_CREATED, items=ITEMS, total_cents=TOTAL, llm=_SlowLLM())
    assert "總計 $195" in text and text.startswith("已收到您的訂單")


def test_provider_without_compose_reply_falls_back():
    text = _compose(rc.OUTCOME_ORDER_CREATED, items=ITEMS, total_cents=TOTAL, llm=object())
    assert text.startswith("已收到您的訂單：\n" + FACT_BLOCK)


def test_needs_review_contains_confirm_and_no_reason_code():
    text = _compose(rc.OUTCOME_NEEDS_REVIEW, reason_code="low_confidence", llm=_WarmLLM())
    assert "確認" in text and "low_confidence" not in text


def test_provider_error_hides_reason_code():
    text = _compose(rc.OUTCOME_PROVIDER_ERROR, reason_code="provider_timeout", llm=_BoomLLM())
    assert text and "provider_timeout" not in text and "provider" not in text


# ── 整合：回覆層 LLM 失敗不影響建單（真 PostgreSQL）──────────────────────────
class _ExtractOkComposeBoomLLM:
    async def extract_order(self, text=None, image_url=None, industry_type="ecom"):
        return ExtractionResult(
            items=[ExtractedItem(product_name="蘋果", quantity=3, evidence="蘋果 x3", confidence_score=0.9)],
            customer_name="王小明", confidence_score=0.9, industry_type="ecom", raw={"src": "test"},
        )

    async def compose_reply(self, outcome, brand_voice=""):
        raise RuntimeError("compose down")


class _Notif:
    def __init__(self):
        self.sent = []

    async def send_message(self, to, text, reply_token=None):
        self.sent.append({"to": to, "text": text, "reply_token": reply_token})


class _BrokenNotif:
    async def send_message(self, to, text, reply_token=None):
        raise RuntimeError("line down")


def _seed(db):
    plan = Plan(name="lite", channel="direct", monthly_price=0)
    db.add(plan)
    db.flush()
    store = Store(name="乖乖商店", industry_type="ecom", market="tw")
    db.add(store)
    db.flush()
    db.add_all([
        User(line_id="Uowner", name="老闆", role="owner", store_id=store.id, plan_id=plan.id),
        Product(store_id=store.id, name="蘋果", aliases=[], unit="顆", price_cents=4500),
    ])
    db.commit()
    return store


def _payload(event_id):
    return {"destination": "Ubot", "events": [{
        "type": "message", "webhookEventId": event_id, "replyToken": "rt-" + event_id,
        "source": {"type": "user", "userId": "Ubuyer"},
        "message": {"type": "text", "text": "蘋果 x3"},
    }]}


def test_worker_compose_failure_still_creates_order_and_sends_canned(db_session, monkeypatch):
    store = _seed(db_session)
    notif = _Notif()
    monkeypatch.setattr("app.providers.get_llm_provider", lambda: _ExtractOkComposeBoomLLM())
    monkeypatch.setattr("app.providers.get_notification_provider", lambda: notif)
    monkeypatch.setattr(line_worker.settings, "default_store_id", store.id)

    asyncio.run(line_worker.process_webhook_event(_payload("compose-boom-1"), db=db_session))

    order = db_session.execute(select(Order)).scalars().one()
    assert order.total_cents == 13500
    assert len(notif.sent) == 1
    assert notif.sent[0]["text"] == "已收到您的訂單：\n蘋果 x3  $135\n總計 $135\n請稍候店家確認。"


def test_worker_send_failure_does_not_block_order(db_session, monkeypatch):
    store = _seed(db_session)
    monkeypatch.setattr("app.providers.get_llm_provider", lambda: _ExtractOkComposeBoomLLM())
    monkeypatch.setattr("app.providers.get_notification_provider", lambda: _BrokenNotif())
    monkeypatch.setattr(line_worker.settings, "default_store_id", store.id)

    asyncio.run(line_worker.process_webhook_event(_payload("send-boom-1"), db=db_session))

    assert db_session.execute(select(func.count(Order.id))).scalar_one() == 1
