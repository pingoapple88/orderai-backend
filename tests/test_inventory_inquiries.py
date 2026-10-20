"""M1-INV-01 人工庫存確認測試。

驗證建立詢問不會建立保留或訂單、人工決策需一次完成、稽核帶 company_id，
以及 JWT/store/company 三層隔離。所有測試使用 Alembic 建立的隔離 PostgreSQL。
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models import AuditLog, Company, Customer, InventoryInquiry, Plan, Product, Store, User
from app.services import inventory_inquiry_service

_MARK = "M1INV_TEST"
_LINE = "Um1inv_test_owner"
_ctx: dict = {}


def _cleanup():
    db = SessionLocal()
    try:
        store_ids = db.execute(select(Store.id).where(Store.name.like(f"{_MARK}%"))).scalars().all()
        if store_ids:
            db.execute(delete(AuditLog).where(AuditLog.store_id.in_(store_ids)))
            db.execute(delete(InventoryInquiry).where(InventoryInquiry.store_id.in_(store_ids)))
            db.execute(delete(Product).where(Product.store_id.in_(store_ids)))
            db.execute(delete(Customer).where(Customer.store_id.in_(store_ids)))
            db.execute(delete(User).where(User.store_id.in_(store_ids)))
            db.execute(delete(Store).where(Store.id.in_(store_ids)))
        db.execute(delete(User).where(User.line_id == _LINE))
        db.execute(delete(Company).where(Company.name.like(f"{_MARK}%")))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def inquiry_context():
    _cleanup()
    db = SessionLocal()
    try:
        plan_id = db.execute(select(Plan.id).order_by(Plan.id)).scalars().first()
        company_a = Company(name=f"{_MARK}_company_a")
        company_b = Company(name=f"{_MARK}_company_b")
        db.add_all([company_a, company_b])
        db.flush()
        store_a = Store(name=f"{_MARK}_A", market="tw", company_id=company_a.id)
        store_b = Store(name=f"{_MARK}_B", market="tw", company_id=company_b.id)
        db.add_all([store_a, store_b])
        db.flush()
        owner = User(line_id=_LINE, name=f"{_MARK}_owner", plan_id=plan_id, store_id=store_a.id, role="owner")
        db.add(owner)
        db.flush()
        product_a = Product(store_id=store_a.id, name="青泉谷高麗菜", aliases=[], unit="顆", price_cents=5000)
        product_b = Product(store_id=store_b.id, name="其他門市商品", aliases=[], unit="盒", price_cents=6000)
        customer_a = Customer(store_id=store_a.id, name=f"{_MARK}_customer")
        db.add_all([product_a, product_b, customer_a])
        db.commit()
        _ctx.update(user_id=owner.id, store_a=store_a.id, store_b=store_b.id,
                    product_a=product_a.id, product_b=product_b.id, customer_a=customer_a.id)
    finally:
        db.close()
    yield _ctx.copy()
    _cleanup()


def _principal(store_id: int) -> dict:
    return {"user_id": _ctx["user_id"], "store_id": store_id, "role": "owner"}


def _headers(store_id: int) -> dict:
    token = create_access_token(_principal(store_id))
    return {"Authorization": f"Bearer {token}"}


def test_create_inquiry_is_pending_and_has_no_reservation(inquiry_context):
    db = SessionLocal()
    try:
        inquiry = inventory_inquiry_service.create_inquiry(
            db, _principal(inquiry_context["store_a"]), inquiry_context["store_a"],
            {
                "requester_name": "王小姐",
                "customer_id": inquiry_context["customer_a"],
                "product_id": inquiry_context["product_a"],
                "requested_product_name": "青泉谷高麗菜",
                "requested_quantity": 2,
                "requested_unit": "顆",
            },
        )
        assert inquiry.status == "pending_review"
        assert inquiry.reviewed_at is None
        audit = db.execute(
            select(AuditLog).where(AuditLog.resource_type == "inventory_inquiry", AuditLog.resource_id == inquiry.id)
        ).scalar_one()
        assert audit.new_value["reservation_created"] is False
        assert audit.new_value["company_id"] is not None
    finally:
        db.close()


def test_review_once_creates_decision_without_order_or_reservation(inquiry_context):
    db = SessionLocal()
    try:
        inquiry = inventory_inquiry_service.create_inquiry(
            db, _principal(inquiry_context["store_a"]), inquiry_context["store_a"],
            {"requested_product_name": "青泉谷高麗菜", "requested_quantity": 1},
        )
        reviewed = inventory_inquiry_service.review_inquiry(
            db, _principal(inquiry_context["store_a"]), inquiry_context["store_a"], inquiry.id,
            "available", "已由攤主人工確認；尚未保留。",
        )
        assert reviewed.status == "available"
        assert reviewed.decision_note == "已由攤主人工確認；尚未保留。"
        assert reviewed.reviewed_at is not None
        with pytest.raises(inventory_inquiry_service.InquiryStateConflict):
            inventory_inquiry_service.review_inquiry(
                db, _principal(inquiry_context["store_a"]), inquiry_context["store_a"], inquiry.id,
                "unavailable", None,
            )
    finally:
        db.close()


def test_cross_store_reference_is_rejected(inquiry_context):
    db = SessionLocal()
    try:
        with pytest.raises(inventory_inquiry_service.InquiryReferenceNotFound):
            inventory_inquiry_service.create_inquiry(
                db, _principal(inquiry_context["store_a"]), inquiry_context["store_a"],
                {
                    "product_id": inquiry_context["product_b"],
                    "requested_product_name": "其他門市商品",
                },
            )
    finally:
        db.close()


def test_api_create_list_review_and_cross_store_403(inquiry_context):
    client = TestClient(app)
    store_a, store_b = inquiry_context["store_a"], inquiry_context["store_b"]
    headers = _headers(store_a)
    create = client.post(
        f"/api/v1/stores/{store_a}/inventory-inquiries", headers=headers,
        json={"requestedProductName": "青泉谷高麗菜", "requestedQuantity": 3, "requestedUnit": "顆"},
    )
    assert create.status_code == 201, create.text
    inquiry_id = create.json()["data"]["id"]
    assert create.json()["data"]["status"] == "pending_review"
    listed = client.get(
        f"/api/v1/stores/{store_a}/inventory-inquiries?status=pending_review", headers=headers,
    )
    assert listed.status_code == 200 and [r["id"] for r in listed.json()["data"]] == [inquiry_id]
    reviewed = client.post(
        f"/api/v1/stores/{store_a}/inventory-inquiries/{inquiry_id}/review", headers=headers,
        json={"decision": "unavailable", "note": "已向攤主確認，今日售罄。"},
    )
    assert reviewed.status_code == 200 and reviewed.json()["data"]["status"] == "unavailable"
    cross_store = client.get(f"/api/v1/stores/{store_b}/inventory-inquiries", headers=headers)
    assert cross_store.status_code == 403
