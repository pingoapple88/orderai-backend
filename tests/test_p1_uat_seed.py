"""青泉谷 P1 OrderAI 隔離 UAT 合成基準測試；全程真 PostgreSQL、零外部服務。"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import BillingRecord, Customer, LineWebhookEvent, Order, Store
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


def test_clear_removes_only_synthetic_baseline(db_session, monkeypatch):
    _configure_uat(monkeypatch)
    p1_uat_seed.seed_p1_uat(db_session)
    p1_uat_seed.clear_p1_uat(db_session)
    assert db_session.execute(select(Store)).scalars().all() == []


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
