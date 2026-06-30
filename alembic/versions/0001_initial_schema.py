"""initial schema — 直接套用 repo 既有 schema.sql（單一真實來源，避免 ORM 漂移）

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-28
"""
from pathlib import Path

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

_TABLES = [
    "audit_logs", "ai_usage_logs", "ai_extractions", "billing_records",
    "order_items", "orders", "user_preferences", "users", "plans", "tenants",
]


def upgrade() -> None:
    schema_sql = (Path(__file__).resolve().parents[2] / "schema.sql").read_text(encoding="utf-8")
    op.execute(schema_sql)


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
