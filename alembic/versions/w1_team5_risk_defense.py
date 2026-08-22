"""Team 5 W1：雙價位方案欄位與解析風險控制設定。

Revision ID: w1_team5_risk_defense
Revises: wo009_batches
Create Date: 2026-08-22
"""
from alembic import op


revision = "w1_team5_risk_defense"
down_revision = "wo009_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE plans ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'direct'"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'plans_name_key' AND conrelid = 'plans'::regclass
            ) THEN
                ALTER TABLE plans DROP CONSTRAINT plans_name_key;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_plans_name_channel' AND conrelid = 'plans'::regclass
            ) THEN
                ALTER TABLE plans ADD CONSTRAINT uq_plans_name_channel UNIQUE (name, channel);
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE plans DROP CONSTRAINT IF EXISTS ck_plans_channel")
    op.execute(
        "ALTER TABLE plans ADD CONSTRAINT ck_plans_channel "
        "CHECK (channel IN ('direct', 'dealer', 'enterprise'))"
    )
    op.execute(
        "INSERT INTO system_settings (key, value, description) VALUES "
        "('ai_confidence_threshold', '0.85', 'AI 訂單自動建單最低信心分數'), "
        "('ai_max_items_per_order', '30', '單筆訂單允許的最大商品列數'), "
        "('ai_max_quantity_per_item', '99', '單一商品允許的最大數量') "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE key IN ('ai_confidence_threshold', 'ai_max_items_per_order', 'ai_max_quantity_per_item')")
    op.execute("ALTER TABLE plans DROP CONSTRAINT IF EXISTS ck_plans_channel")
    op.execute("ALTER TABLE plans DROP CONSTRAINT IF EXISTS uq_plans_name_channel")
    op.execute("ALTER TABLE plans ADD CONSTRAINT plans_name_key UNIQUE (name)")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS channel")
