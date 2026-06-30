"""PR-3：tenants 加 industry_type 欄位（美業架構預留）。

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "industry_type",
            sa.String(length=20),
            nullable=False,
            server_default="ecom",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "industry_type")
