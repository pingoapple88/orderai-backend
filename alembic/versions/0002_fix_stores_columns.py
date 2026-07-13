"""0002_fix_stores_columns — 補 0004 遺漏、squash 時漏進 schema.sql 的欄位。

Revision ID: 0002_fix_stores
Revises: 0001_initial
Create Date: 2026-07-13

背景：squash(0001 baseline)前的 schema.sql 之 stores 缺 4 欄
(company_id/referred_by_dealer_id/plan/line_channel_id)、users 缺 picture_url，
導致 line_callback 建 user+store 時 500。schema.sql 已同步修正(給未來乾淨安裝)；
本增量用 ADD COLUMN IF NOT EXISTS，對「已用舊 schema.sql 建表」的既有環境補欄位，
對乾淨環境(schema.sql 已含)則 no-op。冪等。

這是「schema.sql = baseline、之後變更寫 0002+」規矩的第一次應用。
"""
from alembic import op

revision = "0002_fix_stores"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

# companies / dealers 在 0001(schema.sql)已建，FK 依賴滿足。
_ADDS = [
    "ALTER TABLE stores ADD COLUMN IF NOT EXISTS industry_type VARCHAR(20) DEFAULT 'ecom'",
    "ALTER TABLE stores ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)",
    "ALTER TABLE stores ADD COLUMN IF NOT EXISTS referred_by_dealer_id INTEGER REFERENCES dealers(id)",
    "ALTER TABLE stores ADD COLUMN IF NOT EXISTS plan VARCHAR(50) DEFAULT 'lite'",
    "ALTER TABLE stores ADD COLUMN IF NOT EXISTS line_channel_id VARCHAR(64)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS picture_url TEXT",
]
_DROPS = [
    "ALTER TABLE users DROP COLUMN IF EXISTS picture_url",
    "ALTER TABLE stores DROP COLUMN IF EXISTS line_channel_id",
    "ALTER TABLE stores DROP COLUMN IF EXISTS plan",
    "ALTER TABLE stores DROP COLUMN IF EXISTS referred_by_dealer_id",
    "ALTER TABLE stores DROP COLUMN IF EXISTS company_id",
    "ALTER TABLE stores DROP COLUMN IF EXISTS industry_type",
]


def upgrade() -> None:
    for ddl in _ADDS:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DROPS:
        op.execute(ddl)
