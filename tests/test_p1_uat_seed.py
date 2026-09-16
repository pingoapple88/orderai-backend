"""青泉谷 P1 OrderAI 隔離 UAT 合成基準測試；全程真 PostgreSQL、零外部服務。"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import BillingRecord, Customer, Order, Store
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
