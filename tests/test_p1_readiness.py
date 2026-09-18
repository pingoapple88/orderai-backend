"""Focused PostgreSQL API tests for the read-only, safe P1 readiness preflight."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import get_db
from app.core.security import create_access_token
from app.models import AuditLog, Company, LineWebhookEvent, Plan, Store, User
from app.services import p1_readiness_service
from tests.test_p1_intake import _FERNET_KEY


@dataclass
class _NoSideEffectQueue:
    """A queue sentinel: readiness may acquire it but must not inspect or mutate it."""

    acquired: bool = False

    def depth(self):
        raise AssertionError("readiness must not inspect queue depth")

    def enqueue(self, payload):
        raise AssertionError("readiness must not enqueue")


def _configure_safe_p1(monkeypatch):
    monkeypatch.setattr(p1_readiness_service.settings, "environment", "development")
    monkeypatch.setattr(p1_readiness_service.settings, "p1_intake_enabled", True)
    monkeypatch.setattr(p1_readiness_service.settings, "p1_pii_encryption_key", _FERNET_KEY)
    monkeypatch.setattr(
        p1_readiness_service.settings,
        "p1_identity_hmac_key",
        "p1-readiness-test-hmac-key-material-32b",
    )
    monkeypatch.setattr(p1_readiness_service.settings, "p1_processing_stale_after_seconds", "300")
    monkeypatch.setattr(p1_readiness_service.settings, "p1_erp_ingest_provider", "blocked")
    monkeypatch.setattr(p1_readiness_service.settings, "p1_isolated_delivery_enabled", False)
    monkeypatch.setattr(p1_readiness_service.settings, "p1_uat_delivery_enabled", False)
    monkeypatch.setattr(
        p1_readiness_service.settings,
        "p1_erp_base_url",
        "https://erp.internal.example/secret-path",
    )
    monkeypatch.setattr(
        p1_readiness_service.settings,
        "p1_erp_product_id_map_json",
        '{"123": 987}',
    )


def _seed_scopes(db_session):
    plan = Plan(name="p1-readiness-plan", channel="direct", monthly_price=0)
    company_a = Company(name="P1 readiness company A")
    company_b = Company(name="P1 readiness company B")
    db_session.add_all([plan, company_a, company_b])
    db_session.flush()
    store_a = Store(name="P1 readiness store A", company_id=company_a.id, market="tw")
    store_b = Store(name="P1 readiness store B", company_id=company_b.id, market="tw")
    db_session.add_all([store_a, store_b])
    db_session.flush()
    user = User(
        line_id="p1-readiness-owner",
        name="P1 readiness owner",
        role="owner",
        store_id=store_a.id,
        plan_id=plan.id,
    )
    db_session.add(user)
    db_session.commit()
    return user, company_a, store_a, company_b, store_b


def _event(
    *, company_id, store_id, event_id, status, hmac_value="db-hmac-private", claimed_at=None
):
    return LineWebhookEvent(
        company_id=company_id,
        store_id=store_id,
        channel="line",
        webhook_event_id=event_id,
        event_type="message",
        message_type="text",
        message_id_hmac=hmac_value,
        source_user_hmac=hmac_value,
        status=status,
        claimed_at=claimed_at,
    )


def _headers(user_id: int, store_id: int, role: str = "owner") -> dict[str, str]:
    token = create_access_token({"user_id": user_id, "store_id": store_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


def _api_client(db_session):
    from app.main import app

    def _test_db():
        yield db_session

    app.dependency_overrides[get_db] = _test_db
    return app


@pytest.mark.parametrize("role", ["owner", "manager"])
def test_p1_readiness_api_returns_scoped_safe_counts_without_side_effects(db_session, monkeypatch, role):
    user, company_a, store_a, company_b, store_b = _seed_scopes(db_session)
    _configure_safe_p1(monkeypatch)
    queue = _NoSideEffectQueue()

    def _get_queue():
        queue.acquired = True
        return queue

    monkeypatch.setattr(p1_readiness_service.providers, "get_queue_for_readiness", _get_queue)
    db_session.add_all([
        _event(company_id=company_a.id, store_id=store_a.id, event_id="a-queued", status="queued"),
        _event(company_id=company_a.id, store_id=store_a.id, event_id="a-processing", status="processing"),
        _event(company_id=company_a.id, store_id=store_a.id, event_id="a-failed", status="failed"),
        _event(company_id=company_a.id, store_id=store_a.id, event_id="a-processed", status="processed"),
        _event(company_id=company_b.id, store_id=store_b.id, event_id="b-failed", status="failed", hmac_value="other-store-hmac"),
    ])
    db_session.commit()
    from app import providers

    cached_queue = object()
    monkeypatch.setattr(providers, "_queue_singleton", cached_queue)
    before_events = [
        (row.id, row.status, row.error_code, row.claimed_at, row.processed_at)
        for row in db_session.execute(select(LineWebhookEvent).order_by(LineWebhookEvent.id)).scalars()
    ]
    before_audits = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    app = _api_client(db_session)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/stores/{store_a.id}/p1-intake/readiness",
                headers=_headers(user.id, store_a.id, role),
            )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data == {
            "ready": True,
            "checks": {
                "intakeEnabled": True,
                "storeCompanyScopeResolved": True,
                "encryptionKeyValid": True,
                "identityHmacKeyValid": True,
                "queueProviderAvailable": True,
                "erpDeliveryBlocked": True,
            },
            "unresolvedEventCounts": {"queued": 1, "processing": 1, "failed": 1},
            "staleProcessingCount": 0,
            "hasStaleProcessing": False,
            "reasonCodes": [],
        }
        serialized = str(response.json())
        for forbidden in (
            _FERNET_KEY,
            "p1-readiness-test-hmac-key-material-32b",
            "erp.internal.example",
            "secret-path",
            "123",
            "987",
            "db-hmac-private",
            "other-store-hmac",
            "a-queued",
            "P1 readiness store A",
            "P1 readiness company A",
        ):
            assert forbidden not in serialized
        assert queue.acquired is True
        assert providers._queue_singleton is cached_queue
        assert [
            (row.id, row.status, row.error_code, row.claimed_at, row.processed_at)
            for row in db_session.execute(select(LineWebhookEvent).order_by(LineWebhookEvent.id)).scalars()
        ] == before_events
        assert db_session.execute(select(func.count(AuditLog.id))).scalar_one() == before_audits
    finally:
        app.dependency_overrides.clear()


def test_p1_readiness_api_rejects_cross_store_and_non_manager_roles_before_service(db_session, monkeypatch):
    user, _, store_a, _, store_b = _seed_scopes(db_session)
    _configure_safe_p1(monkeypatch)

    def _must_not_run(*args, **kwargs):
        raise AssertionError("authorization must precede readiness service invocation")

    monkeypatch.setattr(p1_readiness_service, "get_p1_readiness", _must_not_run)
    app = _api_client(db_session)
    try:
        with TestClient(app) as client:
            cross_store = client.get(
                f"/api/v1/stores/{store_b.id}/p1-intake/readiness",
                headers=_headers(user.id, store_a.id, "owner"),
            )
            wrong_role = client.get(
                f"/api/v1/stores/{store_a.id}/p1-intake/readiness",
                headers=_headers(user.id, store_a.id, "staff"),
            )
        assert cross_store.status_code == 403
        assert wrong_role.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_p1_readiness_production_missing_key_is_not_ready_and_never_enables_p1(db_session, monkeypatch):
    user, _, store_a, _, _ = _seed_scopes(db_session)
    _configure_safe_p1(monkeypatch)
    monkeypatch.setattr(p1_readiness_service.settings, "environment", "production")
    monkeypatch.setattr(p1_readiness_service.settings, "p1_pii_encryption_key", "")
    monkeypatch.setattr(p1_readiness_service.providers, "get_queue_for_readiness", _NoSideEffectQueue)
    app = _api_client(db_session)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/stores/{store_a.id}/p1-intake/readiness",
                headers=_headers(user.id, store_a.id),
            )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["ready"] is False
        assert data["checks"]["intakeEnabled"] is True
        assert data["checks"]["encryptionKeyValid"] is False
        assert data["reasonCodes"] == [
            "P1_PII_ENCRYPTION_KEY_MISSING",
            "P1_PRODUCTION_CONFIGURATION_INCOMPLETE",
        ]
        assert p1_readiness_service.settings.p1_intake_enabled is True
        assert p1_readiness_service.settings.p1_isolated_delivery_enabled is False
        assert p1_readiness_service.settings.p1_uat_delivery_enabled is False
    finally:
        app.dependency_overrides.clear()


def test_p1_readiness_reports_invalid_hmac_key_without_exposing_its_value(db_session, monkeypatch):
    user, _, store_a, _, _ = _seed_scopes(db_session)
    _configure_safe_p1(monkeypatch)
    invalid_hmac_key = "too-short"
    monkeypatch.setattr(p1_readiness_service.settings, "p1_identity_hmac_key", invalid_hmac_key)
    monkeypatch.setattr(p1_readiness_service.providers, "get_queue_for_readiness", _NoSideEffectQueue)
    app = _api_client(db_session)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/stores/{store_a.id}/p1-intake/readiness",
                headers=_headers(user.id, store_a.id),
            )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["ready"] is False
        assert data["checks"]["identityHmacKeyValid"] is False
        assert data["reasonCodes"] == ["P1_IDENTITY_HMAC_KEY_INVALID"]
        assert invalid_hmac_key not in str(response.json())
    finally:
        app.dependency_overrides.clear()


def test_p1_readiness_reports_invalid_fernet_and_unavailable_queue_without_network(db_session, monkeypatch):
    user, _, store_a, _, _ = _seed_scopes(db_session)
    _configure_safe_p1(monkeypatch)
    monkeypatch.setattr(p1_readiness_service.settings, "p1_pii_encryption_key", "not-a-fernet-key")

    def _queue_unavailable():
        raise RuntimeError("synthetic provider import failure")

    monkeypatch.setattr(p1_readiness_service.providers, "get_queue_for_readiness", _queue_unavailable)
    app = _api_client(db_session)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/stores/{store_a.id}/p1-intake/readiness",
                headers=_headers(user.id, store_a.id),
            )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["ready"] is False
        assert data["checks"]["encryptionKeyValid"] is False
        assert data["checks"]["queueProviderAvailable"] is False
        assert data["reasonCodes"] == [
            "P1_PII_ENCRYPTION_KEY_INVALID",
            "P1_QUEUE_PROVIDER_UNAVAILABLE",
        ]
    finally:
        app.dependency_overrides.clear()


def test_p1_readiness_reports_only_scoped_stale_processing_without_retrying(db_session, monkeypatch):
    user, company_a, store_a, company_b, store_b = _seed_scopes(db_session)
    _configure_safe_p1(monkeypatch)
    monkeypatch.setattr(p1_readiness_service.settings, "p1_processing_stale_after_seconds", "60")
    monkeypatch.setattr(p1_readiness_service.providers, "get_queue_for_readiness", _NoSideEffectQueue)
    same_company_other_store = Store(
        name="P1 readiness store A alternate",
        company_id=company_a.id,
        market="tw",
    )
    db_session.add(same_company_other_store)
    db_session.flush()
    now = datetime.now(timezone.utc)
    stale_local = _event(
        company_id=company_a.id,
        store_id=store_a.id,
        event_id="local-stale-private",
        status="processing",
        hmac_value="local-stale-hmac-private",
        claimed_at=now - timedelta(seconds=61),
    )
    fresh_local = _event(
        company_id=company_a.id,
        store_id=store_a.id,
        event_id="local-fresh-private",
        status="processing",
        hmac_value="local-fresh-hmac-private",
        claimed_at=now - timedelta(seconds=59),
    )
    stale_same_company_other_store = _event(
        company_id=company_a.id,
        store_id=same_company_other_store.id,
        event_id="same-company-other-store-stale-private",
        status="processing",
        hmac_value="same-company-other-store-stale-hmac-private",
        claimed_at=now - timedelta(days=1),
    )
    stale_other_store = _event(
        company_id=company_b.id,
        store_id=store_b.id,
        event_id="other-stale-private",
        status="processing",
        hmac_value="other-stale-hmac-private",
        claimed_at=now - timedelta(days=1),
    )
    db_session.add_all([
        stale_local,
        fresh_local,
        stale_same_company_other_store,
        stale_other_store,
    ])
    db_session.commit()
    before_events = [
        (row.id, row.status, row.error_code, row.claimed_at, row.processed_at)
        for row in db_session.execute(select(LineWebhookEvent).order_by(LineWebhookEvent.id)).scalars()
    ]
    before_audits = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    app = _api_client(db_session)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/stores/{store_a.id}/p1-intake/readiness",
                headers=_headers(user.id, store_a.id),
            )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["ready"] is False
        assert data["staleProcessingCount"] == 1
        assert data["hasStaleProcessing"] is True
        assert data["reasonCodes"] == ["P1_STALE_PROCESSING_EVENTS"]
        serialized = str(response.json())
        for forbidden in (
            "local-stale-private",
            "local-fresh-private",
            "same-company-other-store-stale-private",
            "other-stale-private",
            "local-stale-hmac-private",
            "local-fresh-hmac-private",
            "same-company-other-store-stale-hmac-private",
            "other-stale-hmac-private",
            str(stale_local.claimed_at),
        ):
            assert forbidden not in serialized
        assert set(data) == {
            "ready",
            "checks",
            "unresolvedEventCounts",
            "staleProcessingCount",
            "hasStaleProcessing",
            "reasonCodes",
        }
        assert [
            (row.id, row.status, row.error_code, row.claimed_at, row.processed_at)
            for row in db_session.execute(select(LineWebhookEvent).order_by(LineWebhookEvent.id)).scalars()
        ] == before_events
        assert db_session.execute(select(func.count(AuditLog.id))).scalar_one() == before_audits
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "threshold, reason_code",
    [
        ("", "P1_PROCESSING_STALE_AFTER_SECONDS_MISSING"),
        ("0", "P1_PROCESSING_STALE_AFTER_SECONDS_INVALID"),
        ("604801", "P1_PROCESSING_STALE_AFTER_SECONDS_INVALID"),
        ("not-a-number", "P1_PROCESSING_STALE_AFTER_SECONDS_INVALID"),
    ],
)
def test_p1_readiness_fails_closed_for_missing_or_invalid_stale_threshold(db_session, monkeypatch, threshold, reason_code):
    user, company_a, store_a, _, _ = _seed_scopes(db_session)
    _configure_safe_p1(monkeypatch)
    monkeypatch.setattr(p1_readiness_service.settings, "p1_processing_stale_after_seconds", threshold)
    monkeypatch.setattr(p1_readiness_service.providers, "get_queue_for_readiness", _NoSideEffectQueue)
    db_session.add(_event(
        company_id=company_a.id,
        store_id=store_a.id,
        event_id="threshold-private-event",
        status="processing",
        hmac_value="threshold-private-hmac",
        claimed_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    db_session.commit()
    before_events = [
        (row.id, row.status, row.error_code, row.claimed_at, row.processed_at)
        for row in db_session.execute(select(LineWebhookEvent).order_by(LineWebhookEvent.id)).scalars()
    ]
    app = _api_client(db_session)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/stores/{store_a.id}/p1-intake/readiness",
                headers=_headers(user.id, store_a.id),
            )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["ready"] is False
        assert data["staleProcessingCount"] == 0
        assert data["hasStaleProcessing"] is False
        assert data["reasonCodes"] == [reason_code]
        assert "processingStaleAfterSeconds" not in data
        if threshold and not threshold.isdecimal():
            assert threshold not in str(response.json())
        assert [
            (row.id, row.status, row.error_code, row.claimed_at, row.processed_at)
            for row in db_session.execute(select(LineWebhookEvent).order_by(LineWebhookEvent.id)).scalars()
        ] == before_events
    finally:
        app.dependency_overrides.clear()
