"""青泉谷 P1 staging UAT Portal：真 PostgreSQL、synthetic-only、零外部服務測試。"""
from __future__ import annotations

import base64
import json
import secrets
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import p1_uat_seed
from app.core.database import get_db
from app.models import (
    AuditLog,
    BillingRecord,
    Company,
    Customer,
    ErpDeliveryOutbox,
    IntakeConversation,
    InventoryInquiry,
    LineWebhookEvent,
    Order,
    Store,
)
from app.services import p1_intake_service, p1_uat_portal_service

_FERNET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
_PORTAL_OPERATOR = "synthetic-uat-operator"


def _configure_portal(monkeypatch) -> str:
    access_code = secrets.token_urlsafe(32)
    settings = p1_uat_portal_service.settings
    monkeypatch.setattr(settings, "p1_uat_portal_enabled", True)
    monkeypatch.setattr(settings, "p1_uat_portal_environment", "staging")
    monkeypatch.setattr(settings, "railway_environment_name", "staging")
    monkeypatch.setattr(settings, "p1_uat_portal_access_code", access_code)
    monkeypatch.setattr(settings, "p1_uat_portal_basic_username", _PORTAL_OPERATOR)
    monkeypatch.setattr(settings, "p1_uat_portal_basic_password", access_code)
    monkeypatch.setattr(settings, "environment", "uat")
    monkeypatch.setattr(settings, "p1_uat_environment_marker", "qingquan-p1-uat")
    monkeypatch.setattr(settings, "p1_uat_seed_enabled", True)
    monkeypatch.setattr(settings, "p1_uat_database_host", "orderai-uat-postgres.railway.internal")
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+psycopg2://uat:placeholder@orderai-uat-postgres.railway.internal:5432/railway",
    )
    monkeypatch.setattr(settings, "p1_pii_encryption_key", _FERNET_KEY)
    monkeypatch.setattr(settings, "p1_identity_hmac_key", secrets.token_urlsafe(32))
    monkeypatch.setattr(settings, "p1_erp_target_company_id", 0)
    monkeypatch.setattr(settings, "p1_erp_sales_location_id", 0)
    monkeypatch.setattr(settings, "p1_erp_product_id_map_json", "{}")
    monkeypatch.setattr(settings, "p1_internal_relay_line_user_ids", "")
    return access_code


def _client(db_session):
    from app.main import app

    def _test_db():
        yield db_session

    app.dependency_overrides[get_db] = _test_db
    return app, TestClient(app)


def _operator_headers(access_code: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{_PORTAL_OPERATOR}:{access_code}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def _headers(access_code: str, *, portal_code: str | None = None) -> dict[str, str]:
    return {
        **_operator_headers(access_code),
        "X-P1-UAT-Access-Code": portal_code if portal_code is not None else access_code,
    }


def _body() -> dict:
    return {
        "buyerAlias": "UAT-買家-不可入 audit",
        "productName": "UAT-商品-不可入 audit",
        "quantity": 3,
        "requestedFor": "2031-02-03T04:05:00+00:00",
        "specialRequirement": "UAT-特殊需求-不可入 audit",
    }


def _seed(db_session, monkeypatch) -> str:
    access_code = _configure_portal(monkeypatch)
    p1_uat_seed.seed_p1_uat(db_session)
    return access_code


def test_html_has_staging_boundaries_and_no_embedded_or_persistent_access_code(db_session, monkeypatch):
    access_code = _configure_portal(monkeypatch)
    app, client = _client(db_session)
    try:
        denied = client.get("/uat/p1")
        assert denied.status_code == 401
        assert denied.headers["www-authenticate"] == 'Basic realm="P1 staging UAT"'

        wrong_operator = client.get("/uat/p1", headers=_operator_headers(f"{access_code}-wrong"))
        assert wrong_operator.status_code == 401

        response = client.get("/uat/p1", headers=_operator_headers(access_code))
        assert response.status_code == 200
        assert "STAGING SYNTHETIC ONLY" in response.text
        assert "不付款／不扣庫／不出貨／不開票" in response.text
        assert "localStorage" not in response.text
        assert "sessionStorage" not in response.text
        assert access_code not in response.text
        assert response.headers["cache-control"] == "no-store"
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_all_json_actions_reject_missing_access_code_before_database_action(db_session, monkeypatch):
    access_code = _configure_portal(monkeypatch)
    app, client = _client(db_session)
    try:
        actions = [
            ("get", "/api/v1/uat/p1/status", None),
            ("post", "/api/v1/uat/p1/cases", _body()),
            ("post", f"/api/v1/uat/p1/cases/{uuid4()}/review", None),
            ("delete", "/api/v1/uat/p1", None),
        ]
        for method, path, body in actions:
            response = client.request(method, path, json=body)
            assert response.status_code == 401
            response = client.request(
                method,
                path,
                json=body,
                headers=_operator_headers(access_code),
            )
            assert response.status_code == 403
        assert db_session.scalar(select(func.count()).select_from(LineWebhookEvent)) == 0
        assert db_session.scalar(select(func.count()).select_from(IntakeConversation)) == 0
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_non_ascii_secret_settings_fail_closed_without_internal_error(db_session, monkeypatch):
    access_code = _configure_portal(monkeypatch)
    app, client = _client(db_session)
    settings = p1_uat_portal_service.settings
    try:
        assert p1_uat_portal_service.constant_time_secret_equals("測試", "測試") is True
        assert p1_uat_portal_service.constant_time_secret_equals("測試", "不同") is False

        monkeypatch.setattr(settings, "p1_uat_portal_basic_password", "非ASCII密碼")
        assert client.get("/uat/p1", headers=_operator_headers(access_code)).status_code == 401

        monkeypatch.setattr(settings, "p1_uat_portal_basic_password", access_code)
        monkeypatch.setattr(settings, "p1_uat_portal_access_code", "非ASCII操作碼")
        response = client.get(
            "/api/v1/uat/p1/status",
            headers=_headers(access_code, portal_code="wrong"),
        )
        assert response.status_code == 403
        assert response.status_code != 500
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_disabled_environment_and_nonexact_code_are_rejected(db_session, monkeypatch):
    access_code = _seed(db_session, monkeypatch)
    app, client = _client(db_session)
    try:
        monkeypatch.setattr(p1_uat_portal_service.settings, "p1_uat_portal_enabled", False)
        assert client.get("/api/v1/uat/p1/status", headers=_headers(access_code)).status_code == 401

        monkeypatch.setattr(p1_uat_portal_service.settings, "p1_uat_portal_enabled", True)
        monkeypatch.setattr(p1_uat_portal_service.settings, "p1_uat_portal_environment", "production")
        assert client.get("/api/v1/uat/p1/status", headers=_headers(access_code)).status_code == 403

        monkeypatch.setattr(p1_uat_portal_service.settings, "p1_uat_portal_environment", "staging")
        monkeypatch.setattr(p1_uat_portal_service.settings, "railway_environment_name", "production")
        assert client.get("/api/v1/uat/p1/status", headers=_headers(access_code)).status_code == 403

        monkeypatch.setattr(p1_uat_portal_service.settings, "railway_environment_name", "staging")
        assert client.get(
            "/api/v1/uat/p1/status",
            headers=_headers(access_code, portal_code=f"{access_code}-not-exact"),
        ).status_code == 403
        monkeypatch.setattr(p1_uat_portal_service.settings, "p1_uat_portal_access_code", "")
        assert client.get(
            "/api/v1/uat/p1/status",
            headers=_headers(access_code),
        ).status_code == 403
        assert db_session.scalar(select(func.count()).select_from(IntakeConversation)) == 0
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_synthetic_database_company_and_store_guards_fail_closed(db_session, monkeypatch):
    access_code = _seed(db_session, monkeypatch)
    app, client = _client(db_session)
    try:
        monkeypatch.setattr(
            p1_uat_portal_service.settings,
            "database_url",
            "postgresql+psycopg2://uat:placeholder@wrong.railway.internal:5432/railway",
        )
        assert client.get("/api/v1/uat/p1/status", headers=_headers(access_code)).status_code == 403

        monkeypatch.setattr(
            p1_uat_portal_service.settings,
            "database_url",
            "postgresql+psycopg2://uat:placeholder@orderai-uat-postgres.railway.internal:5432/railway",
        )
        company = db_session.execute(select(Company)).scalar_one()
        company.name = "非 synthetic 公司"
        db_session.commit()
        assert client.get("/api/v1/uat/p1/status", headers=_headers(access_code)).status_code == 403

        company.name = p1_uat_seed._SYNTHETIC_COMPANY_NAME
        store = db_session.execute(select(Store)).scalar_one()
        store.name = "非 synthetic 店鋪"
        db_session.commit()
        assert client.get("/api/v1/uat/p1/status", headers=_headers(access_code)).status_code == 403
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_create_and_review_are_real_encrypted_pending_only_with_redacted_audit(db_session, monkeypatch):
    access_code = _seed(db_session, monkeypatch)
    app, client = _client(db_session)
    body = _body()
    try:
        created_response = client.post(
            "/api/v1/uat/p1/cases",
            json=body,
            headers=_headers(access_code),
        )
        assert created_response.status_code == 200
        created = created_response.json()["data"]
        assert created["state"] == "needs_human_review"
        assert created["draftEncrypted"] is True
        assert created["erpOutboxCreated"] is False
        assert created["formalSideEffectsCreated"] is False
        response_text = created_response.text
        sensitive_input = (
            body["buyerAlias"],
            body["productName"],
            body["requestedFor"],
            body["specialRequirement"],
        )
        assert all(value not in response_text for value in sensitive_input)

        event = db_session.execute(select(LineWebhookEvent)).scalar_one()
        case = db_session.execute(select(IntakeConversation)).scalar_one()
        assert event.status == "processed"
        assert event.event_type == p1_uat_portal_service._PORTAL_EVENT_TYPE
        assert event.channel == p1_uat_seed._SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL
        assert case.state == "needs_human_review"
        assert case.draft_ciphertext
        assert all(value not in case.draft_ciphertext for value in sensitive_input)
        decrypted = p1_intake_service.decrypt_draft(case.draft_ciphertext)
        assert decrypted["buyer_identity"]["candidate_name"] == body["buyerAlias"]
        assert decrypted["requested_items"][0]["product_name"] == body["productName"]
        assert decrypted["requested_items"][0]["quantity"] == body["quantity"]
        assert decrypted["requested_for"] == body["requestedFor"]
        assert decrypted["special_request"] == body["specialRequirement"]

        reviewed_response = client.post(
            f"/api/v1/uat/p1/cases/{created['caseRef']}/review",
            headers=_headers(access_code),
        )
        assert reviewed_response.status_code == 200
        reviewed = reviewed_response.json()["data"]
        assert reviewed["state"] == "needs_human_review"
        assert reviewed["stateVersion"] == 2
        assert reviewed["reviewedPendingOnly"] is True
        assert reviewed["erpDispatchAttempted"] is False

        db_session.refresh(case)
        assert case.state == "needs_human_review"
        assert db_session.scalar(select(func.count()).select_from(ErpDeliveryOutbox)) == 0
        assert db_session.scalar(select(func.count()).select_from(Customer)) == 0
        assert db_session.scalar(select(func.count()).select_from(Order)) == 0
        assert db_session.scalar(select(func.count()).select_from(BillingRecord)) == 0
        assert db_session.scalar(select(func.count()).select_from(InventoryInquiry)) == 0

        audit_rows = db_session.execute(select(AuditLog)).scalars().all()
        audit_text = json.dumps(
            [
                {
                    "action": row.action,
                    "old": row.old_value,
                    "new": row.new_value,
                }
                for row in audit_rows
            ],
            ensure_ascii=False,
        )
        assert access_code not in audit_text
        assert body["buyerAlias"] not in audit_text
        assert body["productName"] not in audit_text
        assert body["requestedFor"] not in audit_text
        assert body["specialRequirement"] not in audit_text
        assert "p1.uat_portal.event_recorded" in audit_text
        assert "p1.intake.decision" in audit_text
        assert "p1.uat_portal.reviewed_pending" in audit_text

        status_response = client.get(
            "/api/v1/uat/p1/status",
            headers=_headers(access_code),
        )
        assert status_response.status_code == 200
        assert status_response.headers["cache-control"] == "no-store"
        status = status_response.json()["data"]
        assert status["eventLedgerCount"] == 1
        assert status["pendingCaseCount"] == 1
        assert status["encryptedDraftCount"] == 1
        assert status["reviewedPendingCount"] == 1
        assert status["erpOutboxCount"] == 0
        assert status["erpDispatchAttemptCount"] == 0
        assert status["formalCustomerCount"] == 0
        assert status["formalOrderCount"] == 0
        assert status["paymentRecordCount"] == 0
        assert status["inventoryRecordCount"] == 0
        assert status["notApplicableSafetyChecks"] == {
            "fulfillmentRecords": "model_not_present",
            "invoiceRecords": "model_not_present",
        }
        assert all(value not in status_response.text for value in sensitive_input)
        assert access_code not in status_response.text

        repeated = client.post(
            f"/api/v1/uat/p1/cases/{created['caseRef']}/review",
            headers=_headers(access_code),
        )
        assert repeated.status_code == 200
        assert repeated.json()["data"]["alreadyReviewed"] is True
        db_session.refresh(case)
        assert case.state == "needs_human_review"
        assert case.state_version == 2
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_pending_only_invariant_failure_rolls_back_all_portal_writes(db_session, monkeypatch):
    access_code = _seed(db_session, monkeypatch)
    app, client = _client(db_session)
    original_create = p1_uat_portal_service.create_text_case
    before = {
        "events": db_session.scalar(select(func.count()).select_from(LineWebhookEvent)),
        "cases": db_session.scalar(select(func.count()).select_from(IntakeConversation)),
        "audit": db_session.scalar(select(func.count()).select_from(AuditLog)),
    }

    def _invalid_case(*args, **kwargs):
        case = original_create(*args, **kwargs)
        case.state = "approved"
        return case

    monkeypatch.setattr(p1_uat_portal_service, "create_text_case", _invalid_case)
    try:
        response = client.post(
            "/api/v1/uat/p1/cases",
            json=_body(),
            headers=_headers(access_code),
        )
        assert response.status_code == 403
        assert db_session.scalar(select(func.count()).select_from(LineWebhookEvent)) == before["events"]
        assert db_session.scalar(select(func.count()).select_from(IntakeConversation)) == before["cases"]
        assert db_session.scalar(select(func.count()).select_from(AuditLog)) == before["audit"]
        assert db_session.scalar(select(func.count()).select_from(ErpDeliveryOutbox)) == 0
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_cross_store_case_ref_is_not_visible_or_reviewable(db_session, monkeypatch):
    access_code = _seed(db_session, monkeypatch)
    synthetic_store = db_session.execute(
        select(Store).where(Store.store_key == p1_uat_seed._SYNTHETIC_STORE_KEY)
    ).scalar_one()
    other_company = Company(name="其他合成測試公司")
    db_session.add(other_company)
    db_session.flush()
    other_store = Store(
        name="其他合成測試店",
        company_id=other_company.id,
        market="tw",
        industry_type="ecom",
        store_key="other-synthetic-test-store",
    )
    db_session.add(other_store)
    db_session.flush()
    other_ref = str(uuid4())
    other_event = LineWebhookEvent(
        company_id=other_company.id,
        store_id=other_store.id,
        channel=p1_uat_seed._SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
        webhook_event_id=f"{p1_uat_portal_service._PORTAL_EVENT_PREFIX}{other_ref}",
        event_type=p1_uat_portal_service._PORTAL_EVENT_TYPE,
        message_type="text",
        status="processed",
    )
    db_session.add(other_event)
    db_session.flush()
    db_session.add(
        IntakeConversation(
            company_id=other_company.id,
            store_id=other_store.id,
            source_event_id=other_event.id,
            source_kind="text",
            state="needs_human_review",
            state_version=1,
            reason_codes={"codes": ["other_store"]},
        )
    )
    db_session.commit()

    app, client = _client(db_session)
    try:
        status = client.get(
            "/api/v1/uat/p1/status", headers=_headers(access_code)
        ).json()["data"]
        assert status["eventLedgerCount"] == 0
        denied = client.post(
            f"/api/v1/uat/p1/cases/{other_ref}/review",
            headers=_headers(access_code),
        )
        assert denied.status_code == 404
        other_case = db_session.execute(
            select(IntakeConversation).where(
                IntakeConversation.store_id == other_store.id
            )
        ).scalar_one()
        assert other_case.state_version == 1
        assert synthetic_store.id != other_store.id
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_cleanup_is_guarded_and_removes_only_synthetic_dynamic_data(db_session, monkeypatch):
    access_code = _seed(db_session, monkeypatch)
    app, client = _client(db_session)
    try:
        created = client.post(
            "/api/v1/uat/p1/cases",
            json=_body(),
            headers=_headers(access_code),
        )
        assert created.status_code == 200
        synthetic_store = db_session.execute(
            select(Store).where(Store.store_key == p1_uat_seed._SYNTHETIC_STORE_KEY)
        ).scalar_one()
        retained_event = LineWebhookEvent(
            company_id=synthetic_store.company_id,
            store_id=synthetic_store.id,
            channel=p1_uat_seed._SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
            webhook_event_id="other-synthetic-acceptance-must-remain",
            event_type="synthetic_direct_acceptance",
            message_type="text",
            status="processed",
        )
        db_session.add(retained_event)
        db_session.commit()
        audit_count_before = db_session.scalar(select(func.count()).select_from(AuditLog))

        denied = client.delete(
            "/api/v1/uat/p1",
            headers=_headers(access_code, portal_code=f"{access_code}-wrong"),
        )
        assert denied.status_code == 403
        assert db_session.scalar(select(func.count()).select_from(IntakeConversation)) == 1

        cleared = client.delete(
            "/api/v1/uat/p1",
            headers=_headers(access_code),
        )
        assert cleared.status_code == 200
        assert cleared.json()["data"] == {
            "cleared": True,
            "syntheticOnly": True,
            "eventLedgerCount": 0,
            "pendingCaseCount": 0,
            "encryptedDraftCount": 0,
            "auditRetained": True,
            "formalSideEffectsCreated": False,
        }
        remaining_events = db_session.execute(select(LineWebhookEvent)).scalars().all()
        assert [event.webhook_event_id for event in remaining_events] == [
            "other-synthetic-acceptance-must-remain"
        ]
        assert db_session.scalar(select(func.count()).select_from(IntakeConversation)) == 0
        assert db_session.scalar(select(func.count()).select_from(AuditLog)) == audit_count_before + 1
        assert db_session.execute(
            select(Store).where(Store.store_key == p1_uat_seed._SYNTHETIC_STORE_KEY)
        ).scalar_one_or_none() is not None
    finally:
        client.close()
        app.dependency_overrides.clear()
