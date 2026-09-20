"""青泉谷 P1 OrderAI 隔離 UAT 合成基準測試；全程真 PostgreSQL、零外部服務。"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import AuditLog, BillingRecord, Company, Customer, LineWebhookEvent, Order, Plan, Product, Store, User
from app import p1_uat_seed


def _configure_uat(monkeypatch) -> None:
    monkeypatch.setattr(p1_uat_seed.settings, "environment", "uat")
    monkeypatch.setattr(p1_uat_seed.settings, "p1_uat_environment_marker", "qingquan-p1-uat")
    monkeypatch.setattr(p1_uat_seed.settings, "p1_uat_seed_enabled", True)
    monkeypatch.setattr(p1_uat_seed.settings, "p1_uat_database_host", "orderai-uat-postgres.railway.internal")
    monkeypatch.setattr(
        p1_uat_seed.settings,
        "database_url",
        "postgresql+psycopg2://uat:password@orderai-uat-postgres.railway.internal:5432/railway",
    )


def test_seed_is_guarded_by_exact_uat_database_target(db_session, monkeypatch):
    monkeypatch.setattr(p1_uat_seed.settings, "environment", "production")
    monkeypatch.setattr(p1_uat_seed.settings, "p1_uat_environment_marker", "qingquan-p1-uat")
    monkeypatch.setattr(p1_uat_seed.settings, "p1_uat_seed_enabled", True)
    with pytest.raises(p1_uat_seed.P1UatSeedBlocked, match="P1_UAT_ENVIRONMENT_NOT_ALLOWED"):
        p1_uat_seed.seed_p1_uat(db_session)
    assert db_session.execute(select(Store)).scalars().all() == []


def test_seed_is_idempotent_and_creates_no_formal_side_effects(db_session, monkeypatch):
    _configure_uat(monkeypatch)
    initial = p1_uat_seed.seed_p1_uat(db_session)
    repeated = p1_uat_seed.seed_p1_uat(db_session)
    assert initial.created is True and repeated.created is False
    assert (initial.company_id, initial.store_id, initial.owner_user_id, initial.product_id) == (
        repeated.company_id, repeated.store_id, repeated.owner_user_id, repeated.product_id
    )
    assert p1_uat_seed.verify_p1_uat_baseline(db_session)["formal_orders"] == 0
    assert db_session.execute(select(Customer)).scalars().all() == []
    assert db_session.execute(select(Order)).scalars().all() == []
    assert db_session.execute(select(BillingRecord)).scalars().all() == []


def test_clear_refuses_when_formal_side_effect_is_detected(db_session, monkeypatch):
    _configure_uat(monkeypatch)
    seeded = p1_uat_seed.seed_p1_uat(db_session)
    db_session.add(Customer(store_id=seeded.store_id, name="不應存在的測試客戶"))
    db_session.commit()
    with pytest.raises(p1_uat_seed.P1UatSeedBlocked, match="P1_UAT_CLEAR_BLOCKED_BY_FORMAL_SIDE_EFFECT"):
        p1_uat_seed.clear_p1_uat(db_session)


def test_clear_resets_dynamic_data_and_retains_append_only_audit_and_base_assets(db_session, monkeypatch):
    _configure_uat(monkeypatch)
    seeded = p1_uat_seed.seed_p1_uat(db_session)
    audits_before_clear = db_session.execute(
        select(AuditLog).where(AuditLog.store_id == seeded.store_id)
    ).scalars().all()

    p1_uat_seed.clear_p1_uat(db_session)

    assert db_session.get(Company, seeded.company_id) is not None
    assert db_session.get(Store, seeded.store_id) is not None
    assert db_session.get(User, seeded.owner_user_id) is not None
    assert db_session.get(Product, seeded.product_id) is not None
    assert db_session.execute(
        select(Plan).where(
            Plan.name == p1_uat_seed._SYNTHETIC_PLAN_NAME,
            Plan.channel == "direct",
        )
    ).scalar_one_or_none() is not None
    audits_after_clear = db_session.execute(
        select(AuditLog).where(AuditLog.store_id == seeded.store_id)
    ).scalars().all()
    assert len(audits_after_clear) == len(audits_before_clear) + 1

    baseline = p1_uat_seed.verify_p1_uat_baseline(db_session)
    assert baseline["pending_cases"] == 0
    assert baseline["erp_delivery_outbox"] == 0


def test_clear_removes_signed_line_ledger_events_without_permitting_formal_transactions(db_session, monkeypatch):
    _configure_uat(monkeypatch)
    seeded = p1_uat_seed.seed_p1_uat(db_session)
    db_session.add(LineWebhookEvent(
        company_id=seeded.company_id,
        store_id=seeded.store_id,
        channel="line",
        webhook_event_id="qingquan-p1-uat-signed-line-event",
        event_type="message",
        message_type="text",
        message_id_hmac="a" * 64,
        source_user_hmac="b" * 64,
        occurred_at=datetime.now(timezone.utc),
        status="queued",
    ))
    db_session.commit()

    p1_uat_seed.clear_p1_uat(db_session)

    assert db_session.execute(
        select(LineWebhookEvent).where(LineWebhookEvent.store_id == seeded.store_id)
    ).scalars().all() == []
    baseline = p1_uat_seed.verify_p1_uat_baseline(db_session)
    assert baseline["formal_customers"] == 0
    assert baseline["formal_orders"] == 0
    assert baseline["payment_records"] == 0
    assert baseline["line_webhook_events"] == 0


def test_synthetic_direct_event_is_not_treated_as_line_webhook_side_effect(db_session, monkeypatch):
    _configure_uat(monkeypatch)
    seeded = p1_uat_seed.seed_p1_uat(db_session)
    db_session.add(LineWebhookEvent(
        company_id=seeded.company_id,
        store_id=seeded.store_id,
        channel=p1_uat_seed._SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
        webhook_event_id="qingquan-p1-uat-direct-ledger-test",
        event_type="synthetic_direct_acceptance",
        message_type="text",
        message_id_hmac="a" * 64,
        source_user_hmac="b" * 64,
        occurred_at=datetime.now(timezone.utc),
        status="processed",
    ))
    db_session.commit()
    baseline = p1_uat_seed.verify_p1_uat_baseline(db_session)
    assert baseline["line_webhook_events"] == 0
