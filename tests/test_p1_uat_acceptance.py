from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import ErpDeliveryOutbox, IntakeConversation, LineWebhookEvent
from app.p1_uat_seed import seed_p1_uat
from app.services.p1_delivery_service import P1DeliveryBlocked


def test_direct_acceptance_is_disabled_by_default(monkeypatch):
    import app.p1_uat_acceptance as acceptance

    monkeypatch.setattr(acceptance, "settings", SimpleNamespace(
        p1_uat_direct_acceptance_enabled=False,
        p1_intake_enabled=True,
        p1_uat_delivery_enabled=True,
        p1_erp_ingest_provider="http",
    ))
    with pytest.raises(acceptance.P1UatAcceptanceBlocked, match="P1_UAT_DIRECT_ACCEPTANCE_DISABLED"):
        acceptance._assert_direct_acceptance_target()


@pytest.mark.parametrize(
    ("intake_enabled", "delivery_enabled", "provider", "reason"),
    [
        (False, True, "http", "P1_UAT_INTAKE_DISABLED"),
        (True, False, "http", "P1_UAT_DELIVERY_DISABLED"),
        (True, True, "blocked", "P1_UAT_ERP_PROVIDER_NOT_HTTP"),
    ],
)
def test_direct_acceptance_requires_all_explicit_delivery_guards(monkeypatch, intake_enabled, delivery_enabled, provider, reason):
    import app.p1_uat_acceptance as acceptance

    monkeypatch.setattr(acceptance, "settings", SimpleNamespace(
        p1_uat_direct_acceptance_enabled=True,
        p1_intake_enabled=intake_enabled,
        p1_uat_delivery_enabled=delivery_enabled,
        p1_erp_ingest_provider=provider,
    ))
    with pytest.raises(acceptance.P1UatAcceptanceBlocked, match=reason):
        acceptance._assert_direct_acceptance_target()


def _configure_uat(monkeypatch):
    import app.p1_uat_acceptance as acceptance
    import app.p1_uat_seed as seed

    seed_settings = SimpleNamespace(
        environment="uat",
        p1_uat_environment_marker="qingquan-p1-uat",
        p1_uat_seed_enabled=True,
        p1_uat_database_host="orderai-uat-db.railway.internal",
        database_url="postgresql+psycopg2://uat:masked@orderai-uat-db.railway.internal/uat",
    )
    acceptance_settings = SimpleNamespace(
        p1_uat_direct_acceptance_enabled=True,
        p1_intake_enabled=True,
        p1_uat_delivery_enabled=True,
        p1_erp_ingest_provider="http",
    )
    monkeypatch.setattr(seed, "settings", seed_settings)
    monkeypatch.setattr(acceptance, "settings", acceptance_settings)


def _interrupted_exact_case(db_session, monkeypatch):
    import app.p1_uat_acceptance as acceptance

    _configure_uat(monkeypatch)
    baseline = seed_p1_uat(db_session)
    event = LineWebhookEvent(
        company_id=baseline.company_id,
        store_id=baseline.store_id,
        channel="p1_uat_direct",
        webhook_event_id="qingquan-p1-uat-direct-e2e-v1",
        event_type="synthetic_direct_acceptance",
        message_type="text",
        status="processed",
    )
    db_session.add(event)
    db_session.flush()
    case = IntakeConversation(
        company_id=baseline.company_id,
        store_id=baseline.store_id,
        source_event_id=event.id,
        source_kind="synthetic_direct_acceptance",
        state="awaiting_erp_delivery",
        state_version=2,
    )
    db_session.add(case)
    db_session.flush()
    outbox = ErpDeliveryOutbox(
        company_id=baseline.company_id,
        store_id=baseline.store_id,
        conversation_id=case.id,
        idempotency_key="p1-delivery:qingquan-p1-uat-direct-e2e-v1",
        payload_ciphertext="synthetic-test-ciphertext",
        status="queued",
        attempt_count=0,
        last_error_code=None,
    )
    db_session.add(outbox)
    db_session.commit()
    return acceptance, case, outbox


def test_status_is_read_only_and_exposes_no_source_payload(db_session, monkeypatch):
    acceptance, case, outbox = _interrupted_exact_case(db_session, monkeypatch)

    status = acceptance.status_p1_uat_acceptance(db_session)

    assert status == {
        "event_id_sha256": hashlib.sha256(
            b"qingquan-p1-uat-direct-e2e-v1"
        ).hexdigest(),
        "exact_synthetic_event_found": True,
        "case_state": "awaiting_erp_delivery",
        "case_state_version": 2,
        "outbox_status": "queued",
        "outbox_attempt_count": 0,
        "outbox_last_error_code": None,
        "resume_queued_no_attempt_allowed": True,
        "synthetic_only": True,
        "formal_customers": 0,
        "formal_orders": 0,
        "payment_records": 0,
        "line_webhook_events": 0,
        "synthetic_direct_event_count": 1,
        "pending_case_count": 1,
        "erp_delivery_outbox_count": 1,
    }
    assert not db_session.new and not db_session.dirty and not db_session.deleted
    assert db_session.get(IntakeConversation, case.id).state == "awaiting_erp_delivery"
    assert db_session.get(ErpDeliveryOutbox, outbox.id).attempt_count == 0


def test_safe_summary_redacts_database_identifiers_and_keeps_stable_event_evidence():
    from app.p1_uat_acceptance import P1UatAcceptanceResult

    summary = P1UatAcceptanceResult(
        company_id=701,
        store_id=702,
        conversation_id=703,
        outbox_id=704,
        outbox_status="delivered",
        replay_blocked=True,
        reused=False,
    ).safe_summary()

    assert summary == {
        "synthetic_only": True,
        "event_id_sha256": hashlib.sha256(
            b"qingquan-p1-uat-direct-e2e-v1"
        ).hexdigest(),
        "outbox_status": "delivered",
        "replay_blocked": True,
        "reused": False,
        "resumed": False,
        "replay_dispatch_not_attempted": False,
        "line_webhook_enabled": False,
        "line_message_sent": False,
        "formal_customer_created": False,
        "formal_order_created": False,
        "payment_created": False,
        "reservation_created": False,
        "shipment_created": False,
        "invoice_created": False,
    }
    assert not {
        "company_id",
        "store_id",
        "conversation_id",
        "outbox_id",
    }.intersection(summary)


def test_resume_calls_existing_dispatch_once_for_exact_zero_attempt_case(db_session, monkeypatch):
    acceptance, case, outbox = _interrupted_exact_case(db_session, monkeypatch)
    calls = []

    async def _dispatch(db, principal, store_id, conversation_id):
        calls.append((principal["user_id"], store_id, conversation_id))
        current = db.get(ErpDeliveryOutbox, outbox.id)
        current.status = "delivered"
        current.attempt_count = 1
        db.get(IntakeConversation, case.id).state = "closed"
        db.commit()
        return current

    monkeypatch.setattr(acceptance, "dispatch_outbox", _dispatch)
    result = acceptance.resume_p1_uat_queued_no_attempt(db_session)

    assert len(calls) == 1
    assert result.resumed is True and result.outbox_status == "delivered"
    assert result.replay_blocked is False and result.replay_dispatch_not_attempted is True
    assert db_session.get(IntakeConversation, case.id).state == "closed"
    assert db_session.get(ErpDeliveryOutbox, outbox.id).attempt_count == 1


def test_resume_rejects_any_prior_attempt_without_dispatch(db_session, monkeypatch):
    acceptance, _, outbox = _interrupted_exact_case(db_session, monkeypatch)
    outbox.attempt_count = 1
    db_session.commit()

    async def _must_not_dispatch(*args, **kwargs):
        raise AssertionError("已嘗試 outbox 不可經由恢復命令再次交付")

    monkeypatch.setattr(acceptance, "dispatch_outbox", _must_not_dispatch)
    with pytest.raises(acceptance.P1UatAcceptanceBlocked, match="P1_UAT_ACCEPTANCE_RESUME_NOT_ALLOWED"):
        acceptance.resume_p1_uat_queued_no_attempt(db_session)


def test_resume_normalizes_delivery_blocked_error(db_session, monkeypatch):
    acceptance, _, _ = _interrupted_exact_case(db_session, monkeypatch)

    async def _blocked(*args, **kwargs):
        raise P1DeliveryBlocked("P1_ERP_UAT_TARGET_NOT_ALLOWED")

    monkeypatch.setattr(acceptance, "dispatch_outbox", _blocked)
    with pytest.raises(acceptance.P1UatAcceptanceBlocked, match="P1_ERP_UAT_TARGET_NOT_ALLOWED"):
        acceptance.resume_p1_uat_queued_no_attempt(db_session)
