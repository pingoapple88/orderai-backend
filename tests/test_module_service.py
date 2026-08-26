from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.adapters.merchcore_module import OrderAIMerchCoreAdapter
from app.models import AuditLog, Company, ModuleRegistration, Plan, Store, User
from app.services import module_service


def test_manifest_has_five_locales_and_no_event_types_or_price():
    manifest = OrderAIMerchCoreAdapter.module_manifest()

    assert manifest["moduleKey"] == "orderai"
    assert set(manifest["supportedLocales"]) == {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
    assert "monthly_price" not in manifest
    assert "event_types" not in manifest
    assert manifest["registrationEndpoint"].startswith("/api/")


def test_registration_creates_service_state_and_redacted_audit_without_event(db_session):
    registration = module_service.register_self_service(
        db_session,
        company_name="Synthetic Company",
        store_name="Synthetic Store",
        channel="direct",
        locale="fr",
        idempotency_key="module-registration-001",
    )

    store = db_session.get(Store, registration.store_id)
    audit = db_session.execute(select(AuditLog)).scalar_one()
    assert registration.locale == "zh-Hant-TW"
    assert registration.status == "pending_activation"
    assert store.store_key.startswith("ord_")
    assert "Synthetic Company" not in json.dumps(audit.new_value, ensure_ascii=False)
    assert "Synthetic Store" not in json.dumps(audit.new_value, ensure_ascii=False)
    assert "event_id" not in audit.new_value


def test_registration_is_idempotent_and_does_not_create_event(db_session):
    first = module_service.register_self_service(
        db_session,
        company_name="Synthetic Company",
        store_name="Synthetic Store",
        channel="dealer",
        locale="en-US",
        idempotency_key="module-registration-002",
    )
    second = module_service.register_self_service(
        db_session,
        company_name="Ignored On Retry",
        store_name="Ignored On Retry",
        channel="dealer",
        locale="en-US",
        idempotency_key="module-registration-002",
    )

    assert second.id == first.id
    assert len(db_session.execute(select(ModuleRegistration)).scalars().all()) == 1
    assert len(db_session.execute(select(AuditLog)).scalars().all()) == 1


def test_registration_does_not_require_event_registry_settings(db_session):
    registration = module_service.register_self_service(
        db_session,
        company_name="Synthetic Company",
        store_name="Synthetic Store",
        channel="direct",
        locale="zh-Hant-TW",
        idempotency_key="module-registration-no-event-registry",
    )
    assert registration.status == "pending_activation"


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


def test_status_uses_principal_store_scope(db_session):
    registration = module_service.register_self_service(
        db_session,
        company_name="Synthetic Company",
        store_name="Synthetic Store",
        channel="enterprise",
        locale="ja-JP",
        idempotency_key="module-registration-004",
    )
    plan = Plan(name="pending_activation", channel="enterprise", monthly_price=0, ai_extraction_limit=100)
    db_session.add(plan)
    db_session.flush()
    owner = User(
        line_id="U_module_test_owner",
        plan_id=plan.id,
        store_id=registration.store_id,
        role="owner",
        ai_usage_count=3,
    )
    db_session.add(owner)
    db_session.commit()

    status = module_service.get_module_status(
        db_session, principal={"user_id": owner.id, "store_id": registration.store_id, "role": "owner"}
    )

    assert "company_id" not in status
    assert status["channel"] == "enterprise"
    assert status["ai_usage_count"] == 3
    with pytest.raises(HTTPException, match="Tenant scope denied"):
        module_service.get_module_status(db_session, principal={"user_id": owner.id, "store_id": 999999})

    other_company = Company(name="Other Company")
    db_session.add(other_company)
    db_session.flush()
    other_store = Store(name="Other Store", company_id=other_company.id)
    db_session.add(other_store)
    db_session.commit()
    with pytest.raises(HTTPException, match="Tenant scope denied"):
        module_service.get_module_status(
            db_session, principal={"user_id": owner.id, "store_id": other_store.id}
        )
