from fastapi.testclient import TestClient
from app.main import app


def test_health():
    assert TestClient(app).get("/health").json()["status"] == "ok"


def test_models_cover_all_tables():
    # migration 0004（Option A 租戶模型）：tenants → stores，
    # 新增 companies / dealers / customers，表數由 11 增至 14。
    # WO-006：新增 products 型錄表 → 15。
    # WO-009：新增 order_batches / order_commits → 17。
    # W2：新增 module_registrations → 18。
    # M1-INV-01：新增 inventory_inquiries → 19。
    # 青泉谷 P1：事件帳本、對話案例、附件草稿、ERP outbox → 23。
    from app.core.database import Base
    import app.models  # noqa
    assert len(Base.metadata.tables) == 23
    assert "system_settings" in Base.metadata.tables
    assert "products" in Base.metadata.tables  # WO-006 型錄
    assert "order_batches" in Base.metadata.tables  # WO-009
    assert "order_commits" in Base.metadata.tables  # WO-009
    assert "module_registrations" in Base.metadata.tables  # W2 自助註冊
    assert "inventory_inquiries" in Base.metadata.tables  # M1-INV-01 人工庫存確認
    assert "line_webhook_events" in Base.metadata.tables  # P1 驗簽後事件帳本
    assert "intake_conversations" in Base.metadata.tables  # P1 待確認對話草稿
    assert "attachment_drafts" in Base.metadata.tables  # P1 附件人工覆核草稿
    assert "erp_delivery_outbox" in Base.metadata.tables  # P1 受控 ERP 轉送 outbox
    assert "stores" in Base.metadata.tables  # 原 tenants，已改名
    assert "tenants" not in Base.metadata.tables
