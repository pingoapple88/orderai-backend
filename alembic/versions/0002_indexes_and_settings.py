"""PR-2: system_settings 表 + tenant_id 複合索引

Revision ID: 0002_idx_settings
Revises: 0001_initial
Create Date: 2026-06-30
"""
from alembic import op

revision = "0002_idx_settings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_orders_tenant_user ON orders(tenant_id, user_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_tenant_status ON orders(tenant_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_orders_tenant_created ON orders(tenant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_billing_tenant_status ON billing_records(tenant_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_ai_extractions_tenant_status ON ai_extractions(tenant_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_ai_usage_tenant_date ON ai_usage_logs(tenant_id, usage_date)",
    "CREATE INDEX IF NOT EXISTS idx_audit_tenant_created ON audit_logs(tenant_id, created_at)",
]
_SEED = [
    ("ai_soft_limit_pro", "10000", "Pro 方案每月 AI 解析軟上限"),
    ("pre_filter_regex",
     r"(\+\s*\d+|＋\s*\d+|#下單|要買|預購|下單|訂購|\d+\s*份|\d+\s*個|\d+\s*組)",
     "接單意圖預檢正則；不符者略過 LLM"),
    ("polling_interval_minutes", "30", "付款未回調主動輪詢間隔（分）"),
]


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS system_settings ("
        "key VARCHAR(100) PRIMARY KEY, value TEXT, description TEXT, "
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    for k, v, d in _SEED:
        op.execute(
            "INSERT INTO system_settings (key, value, description) "
            f"VALUES ('{k}', '{v}', '{d}') ON CONFLICT (key) DO NOTHING"
        )
    for ddl in _INDEXES:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _INDEXES:
        name = ddl.split("idx_")[1].split(" ")[0]
        op.execute(f"DROP INDEX IF EXISTS idx_{name}")
    op.execute("DROP TABLE IF EXISTS system_settings")
