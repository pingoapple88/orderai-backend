from __future__ import annotations

import hmac
import json
from hashlib import sha256

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.adapters.merchcore_module import OrderAIMerchCoreAdapter
from app.core.config import get_settings
from app.models import AuditLog, ModuleEventOutbox, ModuleRegistration, Plan, Store, User
from app.services import module_service


def _set_signing_secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "module_event_signing_secret", "test-module-secret")


def test_manifest_has_five_locales_and_no_price():
    manifest = OrderAIMerchCoreAdapter.module_manifest()

    assert manifest["module_key"] == "orderai"
    assert set(manifest["supported_locales"]) == {"zh-TW", "en", "th", "ja", "id"}
    assert "monthly_price" not in manifest
    assert manifest["registration_endpoint"].startswith("/api/")


def test_registration_creates_integer_tenant_signed_event_and_redacted_audit(db_session, monkeypatch):
    _set_signing_secret(monkeypatch)

    registration = module_service.register_self_service(
        db_session,
        company_name="Synthetic Company",
        store_name="Synthetic Store",
        channel="direct",
        locale="fr",
        idempotency_key="module-registration-001",
    )

    store = db_session.get(Store, registration.store_id)
    event = db_session.execute(select(ModuleEventOutbox)).scalar_one()
    audit = db_session.execute(select(AuditLog)).scalar_one()
    assert isinstance(registration.company_id, int)
    assert registration.locale == "zh-TW"
    assert store.store_key.startswith("ord_")
    assert event.company_id == registration.company_id
    assert event.event_version == "1.8"
    assert event.payload["store_key"] == store.store_key
    assert "Synthetic Company" not in json.dumps(audit.new_value, ensure_ascii=False)
    assert "Synthetic Store" not in json.dumps(audit.new_value, ensure_ascii=False)
    unsigned = {
        "event_id": event.event_id,
        "event_version": event.event_version,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at,
        "company_id": event.company_id,
        "idempotency_key": event.idempotency_key,
        "payload": event.payload,
    }
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert hmac.compare_digest(
        event.signature,
        hmac.new(b"test-module-secret", canonical.encode("utf-8"), sha256).hexdigest(),
    )


def test_registration_is_idempotent_and_does_not_duplicate_event(db_session, monkeypatch):
    _set_signing_secret(monkeypatch)
    first = module_service.register_self_service(
        db_session,
        company_name="Synthetic Company",
        store_name="Synthetic Store",
        channel="dealer",
        locale="en",
        idempotency_key="module-registration-002",
    )
    second = module_service.register_self_service(
        db_session,
        company_name="Ignored On Retry",
        store_name="Ignored On Retry",
        channel="dealer",
        locale="en",
        idempotency_key="module-registration-002",
    )

    assert second.id == first.id
    assert db_session.execute(select(ModuleRegistration)).scalars().all()[0].id == first.id
    assert len(db_session.execute(select(ModuleEventOutbox)).scalars().all()) == 1


def test_plan_catalog_reads_channel_pricing_without_hardcoding(db_session):
    db_session.add_all(
        [
            Plan(name="starter", channel="direct", monthly_price=39000, ai_extraction_limit=1000),
            Plan(name="starter", channel="dealer", monthly_price=49000, ai_extraction_limit=1000),
        ]
    )
    db_session.commit()

    plans = module_service.list_plans(db_session, channel="direct")

    assert [(plan.name, plan.monthly_price, plan.channel) for plan in plans] == [
        ("starter", 39000, "direct")
    ]


def test_registration_fails_closed_without_event_secret(db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "module_event_signing_secret", "")

    with pytest.raises(RuntimeError, match="MODULE_EVENT_SIGNING_SECRET"):
        module_service.register_self_service(
            db_session,
            company_name="Synthetic Company",
            store_name="Synthetic Store",
            channel="direct",
            locale="zh-TW",
            idempotency_key="module-registration-003",
        )


def test_status_uses_principal_store_scope(db_session, monkeypatch):
    _set_signing_secret(monkeypatch)
    registration = module_service.register_self_service(
        db_session,
        company_name="Synthetic Company",
        store_name="Synthetic Store",
        channel="enterprise",
        locale="ja",
        idempotency_key="module-registration-004",
    )
    plan = Plan(name="pending_activation", channel="enterprise", monthly_price=0, ai_extraction_limit=100)
    db_session.add(plan)
    owner = User(
        line_id="U_module_test_owner",
        plan_id=plan.id if plan.id else 1,
        store_id=registration.store_id,
        role="owner",
        ai_usage_count=3,
    )
    db_session.add(plan)
    db_session.flush()
    owner.plan_id = plan.id
    db_session.add(owner)
    db_session.commit()

    status = module_service.get_module_status(
        db_session, principal={"user_id": owner.id, "store_id": registration.store_id, "role": "owner"}
    )

    assert status["company_id"] == registration.company_id
    assert status["channel"] == "enterprise"
    assert status["ai_usage_count"] == 3
    with pytest.raises(HTTPException, match="Module tenant not found"):
        module_service.get_module_status(db_session, principal={"user_id": owner.id, "store_id": 999999})
