"""青泉谷 P1：事件帳本、附件草稿與 ERP blocked outbox 隔離測試。

所有資料皆為合成值；不呼叫 LINE 媒體下載、OCR/STT、ERP 或付款／庫存服務。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import threading

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import providers
from app.api.v1 import webhook
from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult
from app.models import (
    AttachmentDraft,
    AuditLog,
    Company,
    Customer,
    ErpDeliveryOutbox,
    IntakeConversation,
    LineWebhookEvent,
    Order,
    Plan,
    Product,
    Store,
    User,
)
from app.providers.queue_memory import InMemoryQueue
from app.services import p1_intake_service
from app.workers import line_worker


_FERNET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


class _FakeLLM:
    def __init__(self, result):
        self.result = result

    async def extract_order(self, text=None, image_url=None, industry_type="ecom"):
        return self.result


class _FakeNotif:
    def __init__(self):
        self.sent = []

    async def send_message(self, to, text, reply_token=None):
        self.sent.append({"to": to, "text": text, "reply_token": reply_token})



def _seed(db):
    company = Company(name="青泉谷測試公司")
    plan = Plan(name="p1-test", channel="direct", monthly_price=0)
    db.add_all([company, plan])
    db.flush()
    store = Store(name="青泉谷測試店", company_id=company.id, industry_type="ecom", market="tw")
    db.add(store)
    db.flush()
    user = User(line_id="Up1owner", name="測試店主", role="owner", store_id=store.id, plan_id=plan.id)
    product = Product(store_id=store.id, name="友善雞蛋", aliases=["雞蛋"], unit="盒", price_cents=12000)
    db.add_all([user, product])
    db.commit()
    return company, store



def _configure_p1(monkeypatch, store_id, *, erp_product_map_json="{}"):
    monkeypatch.setattr(line_worker.settings, "p1_intake_enabled", True)
    monkeypatch.setattr(webhook.settings, "p1_intake_enabled", True)
    monkeypatch.setattr(line_worker.settings, "default_store_id", store_id)
    monkeypatch.setattr(webhook.settings, "default_store_id", store_id)
    monkeypatch.setattr(line_worker.settings, "p1_pii_encryption_key", _FERNET_KEY)
    monkeypatch.setattr(webhook.settings, "p1_pii_encryption_key", _FERNET_KEY)
    monkeypatch.setattr(line_worker.settings, "p1_identity_hmac_key", "p1-test-hmac")
    monkeypatch.setattr(webhook.settings, "p1_identity_hmac_key", "p1-test-hmac")
    monkeypatch.setattr(line_worker.settings, "p1_erp_target_company_id", 77)
    monkeypatch.setattr(webhook.settings, "p1_erp_target_company_id", 77)
    monkeypatch.setattr(line_worker.settings, "p1_erp_sales_location_id", 91)
    monkeypatch.setattr(webhook.settings, "p1_erp_sales_location_id", 91)
    monkeypatch.setattr(line_worker.settings, "p1_erp_product_id_map_json", erp_product_map_json)
    monkeypatch.setattr(webhook.settings, "p1_erp_product_id_map_json", erp_product_map_json)
    monkeypatch.setattr(line_worker.settings, "p1_attachment_followup_enabled", False)
    monkeypatch.setattr(webhook.settings, "p1_attachment_followup_enabled", False)
    monkeypatch.setattr(line_worker.settings, "p1_internal_relay_line_user_ids", "")
    monkeypatch.setattr(webhook.settings, "p1_internal_relay_line_user_ids", "")



def _event(event_id="p1-evt-1", message_type="text", text="友善雞蛋 2 盒", user_id="Up1buyer"):
    message = {"type": message_type, "id": f"m-{event_id}"}
    if message_type == "text":
        message["text"] = text
    return {
        "type": "message", "webhookEventId": event_id, "timestamp": 1_789_000_000_000,
        "replyToken": f"rt-{event_id}", "source": {"type": "user", "userId": user_id}, "message": message,
    }



def _payload(*events):
    return {"destination": "Uofficial", "events": list(events)}



def _result(confidence=0.93, requested_for="2026-09-20T02:00:00+00:00", special_request=None):
    raw = {"requested_for": requested_for, "special_request": special_request}
    return ExtractionResult(
        items=[ExtractedItem(product_name="友善雞蛋", quantity=2, unit="盒", evidence="友善雞蛋 2 盒", confidence_score=confidence)],
        customer_name="合成客戶", customer_phone="0900000000", confidence_score=confidence,
        industry_type="ecom", provider_name="test-llm", raw=raw,
    )



def _install_worker(monkeypatch, llm, store_id):
    monkeypatch.setattr("app.providers.get_llm_provider", lambda: llm)
    monkeypatch.setattr("app.providers.get_notification_provider", lambda: _FakeNotif())
    monkeypatch.setattr(line_worker.settings, "default_store_id", store_id)



def _record(db, store, payload):
    return p1_intake_service.record_line_events(db, payload, store)



def _run(payload, db):
    asyncio.run(line_worker.process_webhook_event(payload, db=db))



def _signature(body, secret):
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()



def test_signed_webhook_creates_ledger_once_then_enqueues_once(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    monkeypatch.setattr(webhook.settings, "line_messaging_channel_secret", "test-secret")
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(webhook, "SessionLocal", Session)
    queue = InMemoryQueue()
    providers.set_queue(queue)
    body = json.dumps(_payload(_event())).encode()
    headers = {"X-Line-Signature": _signature(body, "test-secret"), "Content-Type": "application/json"}
    from app.main import app
    client = TestClient(app)
    assert client.post("/api/v1/webhooks/line", content=body, headers=headers).status_code == 200
    assert client.post("/api/v1/webhooks/line", content=body, headers=headers).status_code == 200
    assert db_session.execute(select(func.count(LineWebhookEvent.id))).scalar_one() == 1
    assert queue.depth() == 1



def test_signed_webhook_queue_failure_is_recoverable_by_official_redelivery(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    monkeypatch.setattr(webhook.settings, "line_messaging_channel_secret", "test-secret")
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(webhook, "SessionLocal", Session)

    class FlakyQueue(InMemoryQueue):
        def __init__(self):
            super().__init__()
            self.failed_once = False

        def enqueue(self, payload):
            if not self.failed_once:
                self.failed_once = True
                raise RuntimeError("synthetic queue outage")
            super().enqueue(payload)

    queue = FlakyQueue()
    providers.set_queue(queue)
    body = json.dumps(_payload(_event(event_id="queue-recovery-001"))).encode()
    headers = {"X-Line-Signature": _signature(body, "test-secret"), "Content-Type": "application/json"}
    from app.main import app
    client = TestClient(app)

    first = client.post("/api/v1/webhooks/line", content=body, headers=headers)
    row = db_session.execute(
        select(LineWebhookEvent).where(LineWebhookEvent.webhook_event_id == "queue-recovery-001")
    ).scalar_one()
    db_session.refresh(row)
    assert first.status_code == 503
    assert row.status == "failed"
    assert row.error_code == "P1_QUEUE_ENQUEUE_FAILED"
    assert queue.depth() == 0

    redelivery = client.post("/api/v1/webhooks/line", content=body, headers=headers)
    db_session.refresh(row)
    assert redelivery.status_code == 200
    assert row.status == "queued"
    assert row.error_code is None
    assert queue.depth() == 1
    assert db_session.execute(select(func.count(LineWebhookEvent.id))).scalar_one() == 1



def test_multi_event_partial_enqueue_failure_marks_only_unqueued_suffix_for_official_redelivery(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    monkeypatch.setattr(webhook.settings, "line_messaging_channel_secret", "test-secret")
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(webhook, "SessionLocal", Session)

    class FailsSecondEnqueue(InMemoryQueue):
        def __init__(self):
            super().__init__()
            self.enqueue_count = 0
            self.fail_once = True

        def enqueue(self, payload):
            self.enqueue_count += 1
            if self.fail_once and self.enqueue_count == 2:
                self.fail_once = False
                raise RuntimeError("synthetic second-event queue outage")
            super().enqueue(payload)

    queue = FailsSecondEnqueue()
    providers.set_queue(queue)
    payload = _payload(_event(event_id="partial-enqueue-001"), _event(event_id="partial-enqueue-002"))
    body = json.dumps(payload).encode()
    headers = {"X-Line-Signature": _signature(body, "test-secret"), "Content-Type": "application/json"}
    from app.main import app
    client = TestClient(app)

    assert client.post("/api/v1/webhooks/line", content=body, headers=headers).status_code == 503
    events = {
        row.webhook_event_id: row
        for row in db_session.execute(select(LineWebhookEvent)).scalars()
    }
    assert events["partial-enqueue-001"].status == "queued"
    assert events["partial-enqueue-002"].status == "failed"
    assert events["partial-enqueue-002"].error_code == "P1_QUEUE_ENQUEUE_FAILED"
    assert queue.depth() == 1

    # Official redelivery re-enqueues only the durable failed suffix. It never
    # duplicates the first queued event before the worker claim gate.
    assert client.post("/api/v1/webhooks/line", content=body, headers=headers).status_code == 200
    assert queue.depth() == 2
    _install_worker(monkeypatch, _FakeLLM(_result()), store.id)
    _run(queue.pop(), db_session)
    _run(queue.pop(), db_session)

    events = list(db_session.execute(select(LineWebhookEvent).order_by(LineWebhookEvent.webhook_event_id)).scalars())
    assert [event.status for event in events] == ["processed", "processed"]
    assert all(event.claimed_at is not None for event in events)
    assert db_session.execute(select(func.count(IntakeConversation.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(Order.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(Customer.id))).scalar_one() == 0



def test_processing_event_is_traceable_but_not_rearmed_by_signed_redelivery(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    payload = _payload(_event(event_id="stuck-processing-001"))
    _record(db_session, store, payload)
    claimed = p1_intake_service.claim_event(db_session, store_id=store.id, webhook_event_id="stuck-processing-001")
    assert claimed is not None and claimed.claimed_at is not None

    # No automatic recovery: only a read-only operator surface is available for
    # a worker that died after the durable claim but before case completion.
    assert p1_intake_service.record_line_events(db_session, payload, store) == []
    event = db_session.get(LineWebhookEvent, claimed.id)
    assert event.status == "processing" and event.claimed_at is not None
    assert db_session.execute(select(func.count(IntakeConversation.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(Order.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(Customer.id))).scalar_one() == 0


def test_invalid_signature_creates_no_p1_ledger_or_queue(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    monkeypatch.setattr(webhook.settings, "line_messaging_channel_secret", "test-secret")
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(webhook, "SessionLocal", Session)
    queue = InMemoryQueue()
    providers.set_queue(queue)
    body = json.dumps(_payload(_event())).encode()
    from app.main import app
    response = TestClient(app).post("/api/v1/webhooks/line", content=body, headers={"X-Line-Signature": "bad"})
    assert response.status_code == 401
    assert db_session.execute(select(func.count(LineWebhookEvent.id))).scalar_one() == 0
    assert queue.depth() == 0



def test_missing_p1_encryption_key_rejects_before_ledger_write(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    monkeypatch.setattr(webhook.settings, "line_messaging_channel_secret", "test-secret")
    monkeypatch.setattr(webhook.settings, "p1_pii_encryption_key", "")
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(webhook, "SessionLocal", Session)
    queue = InMemoryQueue()
    providers.set_queue(queue)
    body = json.dumps(_payload(_event(event_id="key-missing"))).encode()
    from app.main import app
    response = TestClient(app).post(
        "/api/v1/webhooks/line",
        content=body,
        headers={"X-Line-Signature": _signature(body, "test-secret"), "Content-Type": "application/json"},
    )
    assert response.status_code == 503
    assert db_session.execute(select(func.count(LineWebhookEvent.id))).scalar_one() == 0
    assert queue.depth() == 0



def test_approved_text_creates_encrypted_p1_draft_and_blocked_outbox_not_local_order(db_session, monkeypatch):
    _, store = _seed(db_session)
    product_id = db_session.execute(select(Product.id)).scalar_one()
    _configure_p1(monkeypatch, store.id, erp_product_map_json=json.dumps({str(product_id): 101}))
    payload = _payload(_event())
    _record(db_session, store, payload)
    _install_worker(monkeypatch, _FakeLLM(_result()), store.id)
    _run(payload, db_session)
    assert db_session.execute(select(func.count(Order.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(Customer.id))).scalar_one() == 0
    case = db_session.execute(select(IntakeConversation)).scalar_one()
    outbox = db_session.execute(select(ErpDeliveryOutbox)).scalar_one()
    assert case.state == "needs_human_review"
    assert outbox.status == "blocked" and outbox.last_error_code == "ERP_CONNECTION_BLOCKED"
    customer_request, order_request = p1_intake_service.build_erp_requests_from_outbox(outbox)
    assert customer_request.company_id == 77 and order_request.company_id == 77
    assert customer_request.line_user_id == "Up1buyer"
    assert order_request.requested_for == "2026-09-20T02:00:00+00:00"
    assert order_request.special_request is None and order_request.items[0].quantity == 2
    assert order_request.items[0].product_id == 101
    audit_serialized = json.dumps([row.new_value for row in db_session.execute(select(AuditLog)).scalars()], ensure_ascii=False)
    assert "友善雞蛋 2 盒" not in audit_serialized and "0900000000" not in audit_serialized



def test_attachment_creates_draft_without_order_or_outbox(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    payload = _payload(_event(event_id="img-1", message_type="image"))
    _record(db_session, store, payload)
    _install_worker(monkeypatch, _FakeLLM(_result()), store.id)
    _run(payload, db_session)
    assert db_session.execute(select(func.count(Order.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(ErpDeliveryOutbox.id))).scalar_one() == 0
    case = db_session.execute(select(IntakeConversation)).scalar_one()
    attachment = db_session.execute(select(AttachmentDraft)).scalar_one()
    assert case.state == "needs_human_review"
    assert attachment.media_type == "image" and attachment.status == "needs_text_confirmation"



def test_low_confidence_stays_human_review_without_erp_delivery(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    payload = _payload(_event(event_id="low-1"))
    _record(db_session, store, payload)
    _install_worker(monkeypatch, _FakeLLM(_result(confidence=0.2)), store.id)
    _run(payload, db_session)
    case = db_session.execute(select(IntakeConversation)).scalar_one()
    assert case.state == "needs_human_review"
    assert db_session.execute(select(func.count(ErpDeliveryOutbox.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(Order.id))).scalar_one() == 0



def test_unknown_catalog_item_stays_human_review_without_erp_delivery(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    payload = _payload(_event(event_id="unknown-product"))
    _record(db_session, store, payload)
    unknown = ExtractionResult(
        items=[ExtractedItem(product_name="不存在的品項", quantity=1, unit="個", evidence="不存在的品項 1", confidence_score=0.99)],
        customer_name="合成客戶", confidence_score=0.99, industry_type="ecom", provider_name="test-llm",
        raw={"requested_for": "2026-09-20T02:00:00+00:00", "special_request": None},
    )
    _install_worker(monkeypatch, _FakeLLM(unknown), store.id)
    _run(payload, db_session)
    case = db_session.execute(select(IntakeConversation)).scalar_one()
    assert case.state == "needs_human_review"
    assert "catalog_item_unmatched" in (case.reason_codes or {}).get("codes", [])
    assert db_session.execute(select(func.count(ErpDeliveryOutbox.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(Order.id))).scalar_one() == 0



def test_internal_relay_uploader_is_not_treated_as_buyer(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    monkeypatch.setattr(line_worker.settings, "p1_internal_relay_line_user_ids", "Ustaff")
    payload = _payload(_event(event_id="relay-1", user_id="Ustaff"))
    _record(db_session, store, payload)
    _install_worker(monkeypatch, _FakeLLM(_result()), store.id)
    _run(payload, db_session)
    case = db_session.execute(select(IntakeConversation)).scalar_one()
    draft = p1_intake_service.decrypt_draft(case.draft_ciphertext)
    assert case.state == "needs_human_review"
    assert draft["uploader_identity"]["line_user_id"] == "Ustaff"
    assert draft["buyer_identity"]["line_user_id"] is None
    assert draft["buyer_identity"]["identity_status"] == "unresolved"
    assert db_session.execute(select(func.count(ErpDeliveryOutbox.id))).scalar_one() == 0



def test_parallel_duplicate_ledger_insert_creates_one_event(db_session, monkeypatch):
    _, store = _seed(db_session)
    _configure_p1(monkeypatch, store.id)
    payload = _payload(_event(event_id="parallel-dup"))
    bind = db_session.get_bind()
    barrier = threading.Barrier(2)
    outcomes = []

    def _record_in_thread():
        session = sessionmaker(bind=bind, autoflush=False, autocommit=False, future=True)()
        try:
            barrier.wait(timeout=3)
            outcomes.append(p1_intake_service.record_line_events(session, payload, store))
        finally:
            session.close()

    threads = [threading.Thread(target=_record_in_thread), threading.Thread(target=_record_in_thread)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(len(result) for result in outcomes) == [0, 1]
    assert db_session.execute(select(func.count(LineWebhookEvent.id))).scalar_one() == 1



def test_same_event_is_processed_once_without_duplicate_case_or_outbox(db_session, monkeypatch):
    _, store = _seed(db_session)
    product_id = db_session.execute(select(Product.id)).scalar_one()
    _configure_p1(monkeypatch, store.id, erp_product_map_json=json.dumps({str(product_id): 101}))
    payload = _payload(_event(event_id="dup-p1"))
    _record(db_session, store, payload)
    _install_worker(monkeypatch, _FakeLLM(_result()), store.id)
    _run(payload, db_session)
    _run(payload, db_session)
    assert db_session.execute(select(func.count(LineWebhookEvent.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(IntakeConversation.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(ErpDeliveryOutbox.id))).scalar_one() == 1




def test_missing_erp_target_company_stays_human_review_without_outbox(db_session, monkeypatch):
    _, store = _seed(db_session)
    product_id = db_session.execute(select(Product.id)).scalar_one()
    _configure_p1(monkeypatch, store.id, erp_product_map_json=json.dumps({str(product_id): 101}))
    monkeypatch.setattr(p1_intake_service.settings, "p1_erp_target_company_id", 0)
    payload = _payload(_event(event_id="erp-target-company-unmapped"))
    _record(db_session, store, payload)
    _install_worker(monkeypatch, _FakeLLM(_result()), store.id)
    _run(payload, db_session)

    case = db_session.execute(select(IntakeConversation)).scalar_one()
    assert case.state == "needs_human_review"
    assert "erp_target_company_unmapped" in (case.reason_codes or {}).get("codes", [])
    assert db_session.execute(select(func.count(ErpDeliveryOutbox.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(Customer.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(Order.id))).scalar_one() == 0
