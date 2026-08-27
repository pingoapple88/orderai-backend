from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models import AuditLog, Company, ModuleRegistration, Plan, Store, User


_MARK = "T5_MODULE_API_"


def _cleanup() -> None:
    db = SessionLocal()
    try:
        company_ids = db.execute(
            select(Company.id).where(Company.name.like(f"{_MARK}%"))
        ).scalars().all()
        if company_ids:
            store_ids = db.execute(
                select(Store.id).where(Store.company_id.in_(company_ids))
            ).scalars().all()
            if store_ids:
                db.execute(delete(AuditLog).where(AuditLog.store_id.in_(store_ids)))
                db.execute(delete(ModuleRegistration).where(ModuleRegistration.store_id.in_(store_ids)))
                db.execute(delete(User).where(User.store_id.in_(store_ids)))
                db.execute(delete(Store).where(Store.id.in_(store_ids)))
            db.execute(delete(Company).where(Company.id.in_(company_ids)))
        db.commit()
    finally:
        db.close()


def _payload(**overrides: str) -> dict[str, str]:
    payload = {
        "companyName": f"{_MARK}Company",
        "storeName": f"{_MARK}Store",
        "channel": "direct",
        "locale": "zh-Hant-TW",
        "idempotencyKey": f"module-api-{uuid.uuid4().hex}",
    }
    payload.update(overrides)
    return payload


def test_public_manifest_has_no_lifecycle_event_advertisement():
    client = TestClient(app)
    response = client.get("/api/v1/module/orderai/manifest")

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data["supportedLocales"]) == {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
    assert "eventTypes" not in data
    assert "monthlyPrice" not in data


def test_registration_api_is_idempotent_and_minimizes_public_response():
    _cleanup()
    client = TestClient(app)
    payload = _payload()
    try:
        first = client.post("/api/v1/module/orderai/registrations", json=payload)
        second = client.post("/api/v1/module/orderai/registrations", json=payload)

        assert first.status_code == 201
        assert second.status_code == 201
        first_data = first.json()["data"]
        second_data = second.json()["data"]
        assert first_data == second_data
        assert first_data["status"] == "pending_activation"
        assert set(first_data) == {"moduleKey", "moduleVersion", "channel", "locale", "status"}

        db = SessionLocal()
        try:
            assert len(db.execute(select(ModuleRegistration)).scalars().all()) == 1
        finally:
            db.close()
    finally:
        _cleanup()


def test_registration_api_rejects_blank_or_unsafe_inputs():
    client = TestClient(app)
    blank = client.post(
        "/api/v1/module/orderai/registrations", json=_payload(companyName="   ")
    )
    unsafe_key = client.post(
        "/api/v1/module/orderai/registrations", json=_payload(idempotencyKey="unsafe key")
    )
    unsupported_locale = client.post(
        "/api/v1/module/orderai/registrations", json=_payload(locale="fr")
    )
    missing_dealer_source = client.post(
        "/api/v1/module/orderai/registrations", json=_payload(channel="dealer")
    )

    assert blank.status_code == 422
    assert unsafe_key.status_code == 422
    assert unsupported_locale.status_code == 422
    assert missing_dealer_source.status_code == 422


def test_registration_api_scopes_same_key_by_company():
    _cleanup()
    client = TestClient(app)
    shared_key = f"same-client-key-{uuid.uuid4().hex}"
    try:
        first = client.post(
            "/api/v1/module/orderai/registrations",
            json=_payload(companyName=f"{_MARK}Company One", idempotencyKey=shared_key),
        )
        second = client.post(
            "/api/v1/module/orderai/registrations",
            json=_payload(companyName=f"{_MARK}Company Two", idempotencyKey=shared_key),
        )

        assert first.status_code == 201
        assert second.status_code == 201
        db = SessionLocal()
        try:
            assert len(db.execute(select(ModuleRegistration)).scalars().all()) == 2
        finally:
            db.close()
    finally:
        _cleanup()


def test_status_api_requires_jwt_store_scope_and_hides_company_identifier():
    _cleanup()
    client = TestClient(app)
    payload = _payload()
    try:
        response = client.post("/api/v1/module/orderai/registrations", json=payload)
        assert response.status_code == 201
        db = SessionLocal()
        try:
            registration = db.execute(
                select(ModuleRegistration)
                .join(Company, ModuleRegistration.company_id == Company.id)
                .where(Company.name == payload["companyName"])
            ).scalar_one()
            plan_id = db.execute(select(Plan.id).order_by(Plan.id)).scalars().first()
            assert plan_id is not None
            user = User(
                line_id=f"U{uuid.uuid4().hex}",
                plan_id=plan_id,
                store_id=registration.store_id,
                role="owner",
            )
            db.add(user)
            db.commit()
            token = create_access_token(
                {"user_id": user.id, "store_id": registration.store_id, "role": "owner"}
            )
        finally:
            db.close()

        missing = client.get("/api/v1/module/orderai/status")
        allowed = client.get(
            "/api/v1/module/orderai/status", headers={"Authorization": f"Bearer {token}"}
        )
        assert missing.status_code == 401
        assert allowed.status_code == 200
        data = allowed.json()["data"]
        assert data["status"] == "pending_activation"
        assert "companyId" not in data
        assert "storeKey" not in data
    finally:
        _cleanup()
