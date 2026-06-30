from fastapi.testclient import TestClient

from app.main import app


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_models_cover_ten_tables():
    from app.core.database import Base
    import app.models  # noqa: F401
    assert len(Base.metadata.tables) == 10
    assert "tenants" in Base.metadata.tables


def test_money_columns_are_integer():
    """鐵律 7：金額欄位為整數型別。"""
    from sqlalchemy import Integer
    from app.models import Plan, Order, OrderItem, BillingRecord
    assert isinstance(Plan.__table__.c.monthly_price.type, Integer)
    assert isinstance(Order.__table__.c.total_amount.type, Integer)
    assert isinstance(OrderItem.__table__.c.unit_price.type, Integer)
    assert isinstance(OrderItem.__table__.c.subtotal.type, Integer)
    assert isinstance(BillingRecord.__table__.c.amount.type, Integer)


def test_tenant_id_on_business_tables():
    """鐵律 3：業務表具 tenant_id 隔離鍵（order_items 除外）。"""
    from app.models import (
        User, UserPreference, Order, BillingRecord,
        AIExtraction, AIUsageLog, AuditLog, OrderItem,
    )
    for model in (User, UserPreference, Order, BillingRecord, AIExtraction, AIUsageLog, AuditLog):
        assert "tenant_id" in model.__table__.c, f"{model.__name__} 缺 tenant_id"
    assert "tenant_id" not in OrderItem.__table__.c
    assert "role" in User.__table__.c
