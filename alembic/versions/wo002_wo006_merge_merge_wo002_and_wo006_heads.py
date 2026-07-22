"""merge wo002 and wo006 heads

Revision ID: wo002_wo006_merge
Revises: 0005_wo002_dedup, wo006_products
Create Date: 2026-07-22 18:13:25.890992
"""
from alembic import op
import sqlalchemy as sa


revision = 'wo002_wo006_merge'
down_revision = ('0005_wo002_dedup', 'wo006_products')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
