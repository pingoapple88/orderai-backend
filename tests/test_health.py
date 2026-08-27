from fastapi.testclient import TestClient
from app.main import app, settings


def test_health():
    body = TestClient(app).get("/health").json()
    assert body["status"] == "ok"
    assert body["releaseSha"] == "unknown"


def test_health_reports_deployment_release_sha(monkeypatch):
    expected_sha = "a" * 40
    monkeypatch.setattr(settings, "release_sha", expected_sha)
    assert TestClient(app).get("/health").json()["releaseSha"] == expected_sha


def test_models_cover_all_tables():
    # migration 0004（Option A 租戶模型）：tenants → stores，
    # 新增 companies / dealers / customers，表數由 11 增至 14。
    # WO-006：新增 products 型錄表 → 15。
    # WO-009：新增 order_batches / order_commits → 17。
    # W2：新增 module_registrations → 18。
    from app.core.database import Base
    import app.models  # noqa
    assert len(Base.metadata.tables) == 18
    assert "system_settings" in Base.metadata.tables
    assert "products" in Base.metadata.tables  # WO-006 型錄
    assert "order_batches" in Base.metadata.tables  # WO-009
    assert "order_commits" in Base.metadata.tables  # WO-009
    assert "module_registrations" in Base.metadata.tables  # W2 自助註冊
    assert "stores" in Base.metadata.tables  # 原 tenants，已改名
    assert "tenants" not in Base.metadata.tables
