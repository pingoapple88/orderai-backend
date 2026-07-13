"""0003_fix_orders_order_items — 補 orders/order_items 缺欄（schema 漂移，WO-002 建單要用）。

Revision ID: 0003_fix_orders
Revises: 0002_fix_stores
Create Date: 2026-07-14

models 有、schema.sql/DB 缺（0004 設計未落到 schema.sql）：
  orders.customer_id / orders.ai_extraction(JSONB) / orders.confirmed_at
  order_items.unit
ADD COLUMN IF NOT EXISTS：對已用舊 schema.sql 建表的環境補欄；乾淨環境(已含)則 no-op。冪等。
WO-002 AI 抄單建單需要 orders.customer_id（綁下單客戶）。
"""
from alembic import op

revision = "0003_fix_orders"
down_revision = "0002_fix_stores"
branch_labels = None
depends_on = None

_ADDS = [
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_id INTEGER REFERENCES customers(id)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ai_extraction JSONB",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP WITH TIME ZONE",
    "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS unit VARCHAR(20) DEFAULT '個'",
]
_DROPS = [
    "ALTER TABLE order_items DROP COLUMN IF EXISTS unit",
    "ALTER TABLE orders DROP COLUMN IF EXISTS confirmed_at",
    "ALTER TABLE orders DROP COLUMN IF EXISTS ai_extraction",
    "ALTER TABLE orders DROP COLUMN IF EXISTS customer_id",
]


def upgrade() -> None:
    for ddl in _ADDS:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DROPS:
        op.execute(ddl)
