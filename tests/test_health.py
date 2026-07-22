from fastapi.testclient import TestClient
from app.main import app


def test_health():
    assert TestClient(app).get("/health").json()["status"] == "ok"


def test_models_cover_all_tables():
    # migration 0004（Option A 租戶模型）：tenants → stores，
    # 新增 companies / dealers / customers，表數由 11 增至 14。
    # WO-006：新增 products 型錄表 → 15。
    # WO-009：新增 order_batches / order_commits → 17。
    from app.core.database import Base
    import app.models  # noqa
    assert len(Base.metadata.tables) == 17
    assert "system_settings" in Base.metadata.tables
    assert "products" in Base.metadata.tables  # WO-006 型錄
    assert "order_batches" in Base.metadata.tables  # WO-009
    assert "order_commits" in Base.metadata.tables  # WO-009
    assert "stores" in Base.metadata.tables  # 原 tenants，已改名
    assert "tenants" not in Base.metadata.tables
