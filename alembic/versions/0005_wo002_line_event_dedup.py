"""0005_wo002_line_event_dedup — WO-002：LINE 抄單去重 + 放寬 customers.dealer_id。

Revision ID: 0005_wo002_dedup
Revises: 0004_add_cust_dealer
Create Date: 2026-07-14

- orders.line_event_id：存 LINE webhookEventId，加 UNIQUE → 一 event 一單（去重靠 DB 約束，
  worker 直接 INSERT 撞 UNIQUE 由 IntegrityError 攔，⛔ 不 check-then-write）。
- customers.dealer_id 放寬 NULLABLE：v0 LINE 客戶無經銷商，需能建無 dealer 的 customer。
  ⛔ 不 drop 欄、不動既有值（既有經銷商客戶 dealer_id 保留）。
全部 IF NOT EXISTS / 冪等。
"""
from alembic import op

revision = "0005_wo002_dedup"
down_revision = "0004_add_cust_dealer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS line_event_id TEXT")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_line_event_id "
        "ON orders(line_event_id)"
    )
    op.execute("ALTER TABLE customers ALTER COLUMN dealer_id DROP NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE customers ALTER COLUMN dealer_id SET NOT NULL")
    op.execute("DROP INDEX IF EXISTS uq_orders_line_event_id")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS line_event_id")
