"""initial schema — 直接套用 repo 既有 schema.sql（單一真實來源，避免 ORM 漂移）

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-28

Squash（方案 D）：原 0002/0003/0004 已刪除。schema.sql 已是完整終態
（14 表 + system_settings/plans seed + store_id 複合索引，皆 IF NOT EXISTS /
ON CONFLICT DO NOTHING），故 0001 執行 schema.sql 即得終態，無須任何增量。
未來變更寫 0002+，正常 alembic 增量，**不得再回頭改 schema.sql 的歷史**。
"""
from pathlib import Path

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

# downgrade 用（DROP ... CASCADE，順序不敏感）。對齊 schema.sql 實際 14 張表。
_TABLES = [
    "companies", "dealers", "customers", "audit_logs", "ai_usage_logs",
    "ai_extractions", "billing_records", "order_items", "orders",
    "user_preferences", "users", "plans", "stores", "system_settings",
]


def upgrade() -> None:
    schema_sql = (Path(__file__).resolve().parents[2] / "schema.sql").read_text(encoding="utf-8")
    op.execute(schema_sql)


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
