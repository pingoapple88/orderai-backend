"""P1 人工覆核與隔離送件測試；全為合成資料，無 LINE、OCR/STT、ERP 實體網路或庫存副作用。"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import create_access_token
from app.core.interfaces.erp_ingest import ErpIngestResult
from app.models import AuditLog, Customer, ErpDeliveryOutbox, IntakeConversation, LineWebhookEvent, Order, Product, User
from app.services import p1_delivery_service, p1_intake_service
from app.workers import line_worker
from tests.test_p1_intake import _FakeLLM, _configure_p1, _event, _install_worker, _payload, _record, _result, _run, _seed


class _AcceptedErp:
    async def create_pending_customer(self, request):
        assert request.idempotency_key.startswith("p1-customer:")
        return ErpIngestResult(provider="isolated-test", reference="71", status="accepted")

    async def submit_pending_confirmation_order(self, request):
        assert request.pending_customer_id == 71
        assert request.idempotency_key.startswith("p1-order:")
        return ErpIngestResult(provider="isolated-test", reference="91", status="accepted")


class _ProviderMustNotRun:
    async def create_pending_customer(self, request):
        raise AssertionError("受控送件守門失敗前不可呼叫 ERP Adapter")

    async def submit_pending_confirmation_order(self, request):
        raise AssertionError("受控送件守門失敗前不可呼叫 ERP Adapter")



def _make_deliverable_case(db_session, monkeypatch):
    _, store = _seed(db_session)
    product_id = db_session.execute(select(Product.id)).scalar_one()
    _configure_p1(monkeypatch, store.id, erp_product_map_json=json.dumps({str(product_id): 101}))
    payload = _payload(_event(event_id="review-delivery-1"))
    _record(db_session, store, payload)
    _install_worker(monkeypatch, _FakeLLM(_result()), store.id)
    _run(payload, db_session)
    return store, db_session.execute(select(IntakeConversation)).scalar_one()



def _principal(db_session, store_id):
    user_id = db_session.execute(select(User.id).where(User.store_id == store_id)).scalar_one()
    return {"user_id": user_id, "store_id": store_id, "role": "owner"}



def _api_client(db_session):
    """以測試資料庫與真實 JWT dependency 驗證 API；不得替換角色或店鋪守衛。"""
    from app.main import app

    def _test_db():
        yield db_session

    app.dependency_overrides[get_db] = _test_db
    return app



def _auth_headers(principal):
    token = create_access_token(principal)
    return {"Authorization": f"Bearer {token}"}



def test_customer_confirmation_is_required_before_isolated_dispatch(db_session, monkeypatch):
    store, case = _make_deliverable_case(db_session, monkeypatch)
    principal = _principal(db_session, store.id)
    reviewed = p1_delivery_service.review_case(
        db_session, principal, store.id, case.id, customer_confirmed=False, note="合成補問中"
    )
    assert reviewed.state == "awaiting_customer_confirmation"
    with pytest.raises(p1_delivery_service.P1DeliveryBlocked) as exc:
        asyncio.run(p1_delivery_service.dispatch_outbox(db_session, principal, store.id, case.id, provider=_AcceptedErp()))
    assert exc.value.reason_code == "P1_ISOLATED_DELIVERY_DISABLED"
    outbox = db_session.execute(select(ErpDeliveryOutbox)).scalar_one()
    assert outbox.status == "blocked" and outbox.attempt_count == 0
    assert db_session.execute(select(Order)).scalars().all() == []
    assert db_session.execute(select(Customer)).scalars().all() == []



def test_human_review_then_explicit_localhost_delivery_closes_case_without_local_order(db_session, monkeypatch):
    store, case = _make_deliverable_case(db_session, monkeypatch)
    principal = _principal(db_session, store.id)
    monkeypatch.setattr(p1_delivery_service.settings, "p1_isolated_delivery_enabled", True)
    monkeypatch.setattr(p1_delivery_service.settings, "p1_erp_base_url", "http://127.0.0.1:8019")
    monkeypatch.setattr(p1_delivery_service.settings, "p1_erp_isolated_allowed_hosts", "localhost,127.0.0.1")
    p1_delivery_service.review_case(db_session, principal, store.id, case.id, customer_confirmed=True)
    delivered = asyncio.run(p1_delivery_service.dispatch_outbox(
        db_session, principal, store.id, case.id, provider=_AcceptedErp()
    ))
    refreshed_case = db_session.get(IntakeConversation, case.id)
    assert delivered.status == "delivered" and delivered.attempt_count == 1
    assert refreshed_case.state == "closed" and refreshed_case.state_version == 3
    assert db_session.execute(select(Order)).scalars().all() == []
    assert db_session.execute(select(Customer)).scalars().all() == []
    audit_text = json.dumps([row.new_value for row in db_session.execute(select(AuditLog)).scalars()], ensure_ascii=False)
    assert "0900000000" not in audit_text and "友善雞蛋 2 盒" not in audit_text



def test_isolated_delivery_rejects_nonlocal_target_before_provider_is_called(db_session, monkeypatch):
    store, case = _make_deliverable_case(db_session, monkeypatch)
    principal = _principal(db_session, store.id)
    monkeypatch.setattr(p1_delivery_service.settings, "p1_isolated_delivery_enabled", True)
    monkeypatch.setattr(p1_delivery_service.settings, "p1_erp_base_url", "https://example.invalid")
    p1_delivery_service.review_case(db_session, principal, store.id, case.id, customer_confirmed=True)
    with pytest.raises(p1_delivery_service.P1DeliveryBlocked) as exc:
        asyncio.run(p1_delivery_service.dispatch_outbox(db_session, principal, store.id, case.id, provider=_AcceptedErp()))
    assert exc.value.reason_code == "P1_ERP_TARGET_NOT_ISOLATED"
    assert db_session.execute(select(ErpDeliveryOutbox)).scalar_one().attempt_count == 0



def _configure_external_uat_delivery(monkeypatch):
    monkeypatch.setattr(p1_delivery_service.settings, "p1_isolated_delivery_enabled", False)
    monkeypatch.setattr(p1_delivery_service.settings, "p1_uat_delivery_enabled", True)
    monkeypatch.setattr(p1_delivery_service.settings, "environment", "uat")
    monkeypatch.setattr(p1_delivery_service.settings, "p1_uat_environment_marker", "qingquan-p1-uat")
    monkeypatch.setattr(
        p1_delivery_service.settings,
        "p1_erp_base_url",
        "https://merchcore-platform-uat.example.test",
    )
    monkeypatch.setattr(
        p1_delivery_service.settings,
        "p1_erp_uat_allowed_hosts",
        "merchcore-platform-uat.example.test",
    )



def test_external_uat_delivery_requires_all_explicit_guards_before_provider_is_called(db_session, monkeypatch):
    store, case = _make_deliverable_case(db_session, monkeypatch)
    principal = _principal(db_session, store.id)
    _configure_external_uat_delivery(monkeypatch)
    p1_delivery_service.review_case(db_session, principal, store.id, case.id, customer_confirmed=True)

    delivered = asyncio.run(p1_delivery_service.dispatch_outbox(
        db_session, principal, store.id, case.id, provider=_AcceptedErp()
    ))

    assert delivered.status == "delivered"
    assert db_session.get(IntakeConversation, case.id).state == "closed"
    assert db_session.execute(select(Order)).scalars().all() == []
    assert db_session.execute(select(Customer)).scalars().all() == []


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    [
        ("p1_uat_delivery_enabled", False, "P1_ISOLATED_DELIVERY_DISABLED"),
        ("environment", "production", "P1_UAT_ENVIRONMENT_NOT_ALLOWED"),
        ("p1_uat_environment_marker", "", "P1_UAT_MARKER_INVALID"),
        ("p1_erp_uat_allowed_hosts", "other-uat.example.test", "P1_ERP_UAT_TARGET_NOT_ALLOWED"),
    ],
)
def test_external_uat_delivery_fails_closed_for_missing_or_production_guards(
    db_session, monkeypatch, field, value, reason_code
):
    store, case = _make_deliverable_case(db_session, monkeypatch)
    principal = _principal(db_session, store.id)
    _configure_external_uat_delivery(monkeypatch)
    monkeypatch.setattr(p1_delivery_service.settings, field, value)
    p1_delivery_service.review_case(db_session, principal, store.id, case.id, customer_confirmed=True)

    with pytest.raises(p1_delivery_service.P1DeliveryBlocked) as exc:
        asyncio.run(p1_delivery_service.dispatch_outbox(
            db_session, principal, store.id, case.id, provider=_ProviderMustNotRun()
        ))

    assert exc.value.reason_code == reason_code
    outbox = db_session.execute(select(ErpDeliveryOutbox)).scalar_one()
    assert outbox.status == "queued" and outbox.attempt_count == 0



def test_external_uat_delivery_requires_https_even_for_exact_allowed_host(db_session, monkeypatch):
    store, case = _make_deliverable_case(db_session, monkeypatch)
    principal = _principal(db_session, store.id)
    _configure_external_uat_delivery(monkeypatch)
    monkeypatch.setattr(
        p1_delivery_service.settings,
        "p1_erp_base_url",
        "http://merchcore-platform-uat.example.test",
    )
    p1_delivery_service.review_case(db_session, principal, store.id, case.id, customer_confirmed=True)

    with pytest.raises(p1_delivery_service.P1DeliveryBlocked) as exc:
        asyncio.run(p1_delivery_service.dispatch_outbox(
            db_session, principal, store.id, case.id, provider=_ProviderMustNotRun()
        ))

    assert exc.value.reason_code == "P1_UAT_HTTPS_REQUIRED"



def test_p1_intake_api_rejects_cross_store_owner_before_case_access(db_session, monkeypatch):
    store, case = _make_deliverable_case(db_session, monkeypatch)
    principal = _principal(db_session, store.id)
    app = _api_client(db_session)
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/stores/{store.id + 999}/p1-intake/{case.id}/review",
                json={"customerConfirmed": True},
                headers=_auth_headers(principal),
            )
        assert response.status_code == 403
        assert db_session.get(IntakeConversation, case.id).state == "needs_human_review"
        assert db_session.execute(select(ErpDeliveryOutbox)).scalar_one().status == "blocked"
    finally:
        app.dependency_overrides.clear()



def test_p1_intake_api_enforces_review_and_dispatch_state_conflicts(db_session, monkeypatch):
    store, case = _make_deliverable_case(db_session, monkeypatch)
    principal = _principal(db_session, store.id)
    app = _api_client(db_session)
    try:
        with TestClient(app) as client:
            dispatch_before_review = client.post(
                f"/api/v1/stores/{store.id}/p1-intake/{case.id}/dispatch",
                headers=_auth_headers(principal),
            )
            assert dispatch_before_review.status_code == 422
            assert dispatch_before_review.json()["error"]["message"] == "P1_ISOLATED_DELIVERY_DISABLED"

            approved = client.post(
                f"/api/v1/stores/{store.id}/p1-intake/{case.id}/review",
                json={"customerConfirmed": True, "note": "已由合成人工覆核確認"},
                headers=_auth_headers(principal),
            )
            assert approved.status_code == 200
            assert approved.json()["data"]["state"] == "awaiting_erp_delivery"

            repeated_review = client.post(
                f"/api/v1/stores/{store.id}/p1-intake/{case.id}/review",
                json={"customerConfirmed": True},
                headers=_auth_headers(principal),
            )
        assert repeated_review.status_code == 409
        assert db_session.get(IntakeConversation, case.id).state == "awaiting_erp_delivery"
        outbox = db_session.execute(select(ErpDeliveryOutbox)).scalar_one()
        assert outbox.status == "queued" and outbox.attempt_count == 0
    finally:
        app.dependency_overrides.clear()




def test_p1_event_api_lists_only_scoped_unresolved_metadata_without_pii_or_rearm(db_session, monkeypatch):
    store, _ = _make_deliverable_case(db_session, monkeypatch)
    event = db_session.execute(select(LineWebhookEvent)).scalar_one()
    event.status = "failed"
    event.error_code = "P1_INTAKE_PROCESSING_FAILED"
    db_session.commit()
    principal = _principal(db_session, store.id)
    app = _api_client(db_session)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/stores/{store.id}/p1-intake/events?status=failed",
                headers=_auth_headers(principal),
            )
            denied = client.get(
                f"/api/v1/stores/{store.id + 999}/p1-intake/events",
                headers=_auth_headers(principal),
            )
            low_role_denied = client.get(
                f"/api/v1/stores/{store.id}/p1-intake/events",
                headers=_auth_headers({**principal, "role": "staff"}),
            )
        assert response.status_code == 200
        row = response.json()["data"][0]
        assert row["status"] == "failed"
        assert row["errorCode"] == "P1_INTAKE_PROCESSING_FAILED"
        assert "sourceUserHmac" not in row and "messageIdHmac" not in row
        assert denied.status_code == 403
        assert low_role_denied.status_code == 403
        assert db_session.execute(select(Order)).scalars().all() == []
        assert db_session.execute(select(Customer)).scalars().all() == []
    finally:
        app.dependency_overrides.clear()
