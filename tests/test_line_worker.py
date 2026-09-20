"""Issue #34 focused LINE worker tests against the migrated PostgreSQL fixture.

The worker may create only existing P1 ledger-backed review cases. All fixtures
are synthetic; no LINE or ERP network calls occur.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging

from sqlalchemy import func, select

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult
from app.models import (
    Company,
    Customer,
    ErpDeliveryOutbox,
    IntakeConversation,
    LineWebhookEvent,
    Order,
    Plan,
    Product,
    Store,
)
from app.services import p1_intake_service
from app.workers import line_worker


_FERNET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


class _FakeLLM:
    def __init__(self, result):
        self.result = result

    async def extract_order(self, text=None, image_url=None, industry_type="ecom"):
        return self.result


class _FakeNotif:
    async def send_message(self, to, text, reply_token=None):
        raise AssertionError("text intake must not automatically promise a sale")


class _CapturingNotif:
    def __init__(self):
        self.messages = []

    async def send_message(self, to, text, reply_token=None):
        self.messages.append({"to": to, "text": text, "reply_token": reply_token})


def _seed(db):
    company = Company(name="Issue 34 合成公司")
    plan = Plan(name="issue34", channel="direct", monthly_price=0)
    db.add_all([company, plan])
    db.flush()
    store = Store(name="Issue 34 合成店", company_id=company.id, industry_type="ecom", market="tw")
    db.add(store)
    db.flush()
    product = Product(store_id=store.id, name="友善雞蛋", aliases=["雞蛋"], unit="盒", price_cents=12000)
    db.add(product)
    db.commit()
    return store, product


def _configure_p1(monkeypatch, store_id, product_id):
    monkeypatch.setattr(line_worker.settings, "p1_intake_enabled", True)
    monkeypatch.setattr(line_worker.settings, "default_store_id", store_id)
    monkeypatch.setattr(line_worker.settings, "p1_pii_encryption_key", _FERNET_KEY)
    monkeypatch.setattr(line_worker.settings, "p1_identity_hmac_key", "issue34-synthetic-hmac")
    monkeypatch.setattr(line_worker.settings, "p1_erp_target_company_id", 77)
    monkeypatch.setattr(line_worker.settings, "p1_erp_sales_location_id", 91)
    monkeypatch.setattr(
        line_worker.settings,
        "p1_erp_product_id_map_json",
        json.dumps({str(product_id): 101}),
    )
    monkeypatch.setattr(line_worker.settings, "p1_attachment_followup_enabled", False)
    monkeypatch.setattr(line_worker.settings, "p1_internal_relay_line_user_ids", "")


def _result(*, confidence=0.96):
    return ExtractionResult(
        items=[
            ExtractedItem(
                product_name="友善雞蛋",
                quantity=2,
                unit="盒",
                evidence="友善雞蛋 2 盒",
                confidence_score=confidence,
            )
        ],
        customer_name="合成買方",
        customer_phone="0900000000",
        confidence_score=confidence,
        industry_type="ecom",
        provider_name="synthetic-llm",
        raw={
            "requested_for": "2026-09-20T02:00:00+00:00",
            "special_request": "送達前電話確認",
        },
    )


def _payload(event_id="issue34-event"):
    return {
        "destination": "Uofficial",
        "events": [
            {
                "type": "message",
                "webhookEventId": event_id,
                "timestamp": 1_789_000_000_000,
                "replyToken": f"reply-{event_id}",
                "source": {"type": "user", "userId": "Uissue34buyer"},
                "message": {
                    "type": "text",
                    "id": f"message-{event_id}",
                    "text": "合成買方訂友善雞蛋 2 盒，2026-09-20 10:00+00:00，需要送達前電話確認",
                },
            }
        ],
    }


def _record(db, store, payload):
    return p1_intake_service.record_line_events(db, payload, store)


def _run(monkeypatch, result, payload, db, *, notif=None):
    monkeypatch.setattr("app.providers.get_llm_provider", lambda: _FakeLLM(result))
    monkeypatch.setattr("app.providers.get_notification_provider", lambda: notif or _FakeNotif())
    asyncio.run(line_worker.process_webhook_event(payload, db=db))


def _count(db, model):
    return db.execute(select(func.count(model.id))).scalar_one()


def test_complete_five_field_text_only_creates_human_review_case_no_formal_customer_or_order(db_session, monkeypatch):
    store, product = _seed(db_session)
    _configure_p1(monkeypatch, store.id, product.id)
    payload = _payload()
    assert _record(db_session, store, payload)

    _run(monkeypatch, _result(), payload, db_session)

    case = db_session.execute(select(IntakeConversation)).scalar_one()
    outbox = db_session.execute(select(ErpDeliveryOutbox)).scalar_one()
    assert case.state == "needs_human_review"
    assert outbox.status == "blocked"
    assert outbox.last_error_code == "ERP_CONNECTION_BLOCKED"
    assert _count(db_session, Customer) == 0
    assert _count(db_session, Order) == 0
    assert _count(db_session, LineWebhookEvent) == 1


def test_low_confidence_text_stays_human_review_without_delivery_or_formal_records(db_session, monkeypatch):
    store, product = _seed(db_session)
    _configure_p1(monkeypatch, store.id, product.id)
    payload = _payload("issue34-low-confidence")
    assert _record(db_session, store, payload)

    _run(monkeypatch, _result(confidence=0.20), payload, db_session)

    case = db_session.execute(select(IntakeConversation)).scalar_one()
    assert case.state == "needs_human_review"
    assert "confidence_below_threshold" in (case.reason_codes or {}).get("codes", [])
    assert _count(db_session, ErpDeliveryOutbox) == 0
    assert _count(db_session, Customer) == 0
    assert _count(db_session, Order) == 0


def test_sticker_creates_human_review_case_and_only_asks_for_text_clarification(db_session, monkeypatch):
    store, product = _seed(db_session)
    _configure_p1(monkeypatch, store.id, product.id)
    monkeypatch.setattr(line_worker.settings, "p1_attachment_followup_enabled", True)
    monkeypatch.setattr(line_worker.settings, "line_messaging_access_token", "synthetic-test-token")
    payload = _payload("issue34-sticker")
    payload["events"][0]["message"] = {
        "type": "sticker",
        "id": "synthetic-sticker-message",
        "packageId": "synthetic-package",
        "stickerId": "synthetic-sticker",
    }
    assert _record(db_session, store, payload)
    notif = _CapturingNotif()

    _run(monkeypatch, _result(), payload, db_session, notif=notif)

    case = db_session.execute(select(IntakeConversation)).scalar_one()
    event = db_session.execute(select(LineWebhookEvent)).scalar_one()
    assert case.state == "needs_human_review"
    assert case.source_kind == "sticker"
    assert "unsupported_message_type" in (case.reason_codes or {}).get("codes", [])
    assert event.status == "processed"
    assert _count(db_session, ErpDeliveryOutbox) == 0
    assert _count(db_session, Customer) == 0
    assert _count(db_session, Order) == 0
    assert notif.messages == [{
        "to": "Uissue34buyer",
        "reply_token": "reply-issue34-sticker",
        "text": "已收到貼圖。為避免辨識錯誤，請直接以文字提供訂購人、商品、數量、需要時間與特別要求。",
    }]


def test_redelivery_claims_existing_ledger_event_once_without_duplicate_case_or_formal_records(db_session, monkeypatch, caplog):
    store, product = _seed(db_session)
    _configure_p1(monkeypatch, store.id, product.id)
    event_id = "issue34-redelivery"
    payload = _payload(event_id)
    assert _record(db_session, store, payload)
    assert _record(db_session, store, payload) == []

    _run(monkeypatch, _result(), payload, db_session)
    with caplog.at_level(logging.INFO, logger="app.workers.line_worker"):
        _run(monkeypatch, _result(), payload, db_session)

    assert _count(db_session, LineWebhookEvent) == 1
    assert _count(db_session, IntakeConversation) == 1
    assert _count(db_session, ErpDeliveryOutbox) == 1
    assert _count(db_session, Customer) == 0
    assert _count(db_session, Order) == 0
    messages = "\n".join(caplog.messages)
    assert event_id not in messages
    assert hashlib.sha256(event_id.encode("utf-8")).hexdigest() in messages


def test_missing_encryption_configuration_fails_closed_after_claim_without_formal_records(db_session, monkeypatch):
    store, product = _seed(db_session)
    _configure_p1(monkeypatch, store.id, product.id)
    payload = _payload("issue34-key-missing")
    assert _record(db_session, store, payload)
    monkeypatch.setattr(line_worker.settings, "p1_pii_encryption_key", "")

    _run(monkeypatch, _result(), payload, db_session)

    event = db_session.execute(select(LineWebhookEvent)).scalar_one()
    assert event.status == "failed"
    assert event.error_code == "P1_PII_ENCRYPTION_KEY_MISSING"
    assert _count(db_session, IntakeConversation) == 0
    assert _count(db_session, ErpDeliveryOutbox) == 0
    assert _count(db_session, Customer) == 0
    assert _count(db_session, Order) == 0


def test_disabled_p1_worker_fails_closed_without_claiming_or_creating_formal_records(db_session, monkeypatch):
    store, product = _seed(db_session)
    _configure_p1(monkeypatch, store.id, product.id)
    payload = _payload("issue34-p1-disabled")
    assert _record(db_session, store, payload)
    monkeypatch.setattr(line_worker.settings, "p1_intake_enabled", False)

    _run(monkeypatch, _result(), payload, db_session)

    event = db_session.execute(select(LineWebhookEvent)).scalar_one()
    assert event.status == "queued"
    assert _count(db_session, IntakeConversation) == 0
    assert _count(db_session, Customer) == 0
    assert _count(db_session, Order) == 0
