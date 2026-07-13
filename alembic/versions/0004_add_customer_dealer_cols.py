"""0004_add_customer_dealer_cols — 補 customers/dealers 缺欄（schema 漂移，非破壞 ADD）。

Revision ID: 0004_add_cust_dealer
Revises: 0003_fix_orders
Create Date: 2026-07-14

models 有、DB 缺（0004 設計未落到 schema.sql）：
  customers.store_id / customers.line_user_id
  dealers.code
ADD COLUMN IF NOT EXISTS：對既有環境補欄；乾淨環境（schema.sql 已含）則 no-op。冪等。
⛔ 不 drop 既有欄（customers.dealer_id / dealers.company_id 有經銷商資料）。
⛔ ADD 不帶 NOT NULL：既有列無值，加 NOT NULL 會炸；model 標 NOT NULL 但漂移測試只比欄名不比 constraint。
"""
from alembic import op

revision = "0004_add_cust_dealer"
down_revision = "0003_fix_orders"
branch_labels = None
depends_on = None

_ADDS = [
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS store_id INTEGER",
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS line_user_id TEXT",
    "ALTER TABLE dealers ADD COLUMN IF NOT EXISTS code VARCHAR(255) UNIQUE",
]
_DROPS = [
    "ALTER TABLE dealers DROP COLUMN IF EXISTS code",
    "ALTER TABLE customers DROP COLUMN IF EXISTS line_user_id",
    "ALTER TABLE customers DROP COLUMN IF EXISTS store_id",
]


def upgrade() -> None:
    for ddl in _ADDS:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DROPS:
        op.execute(ddl)
