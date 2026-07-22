"""wo009_batches_paste_ingest — 開團批次 + 貼上抄單去重（WO-009）。

Revision ID: wo009_batches
Revises: wo002_wo006_merge
Create Date: 2026-07-21

- order_batches：開團批次（store_id NOT NULL + index；status open|closed）。
- order_commits：commit 去重（UNIQUE(batch_id, raw_text_sha256)）。
- orders.batch_id：所屬批次（NULL，index）。
id/store_id/batch_id 依既有 schema 用 INTEGER（契約寫 uuid 與既有牴觸，以既有為準）。
本表無金額欄位（律七不適用；金額仍在 orders/order_items 之 *_cents）。
CREATE TABLE / ADD COLUMN IF NOT EXISTS：冪等，對齊既有 migration 風格。
"""
from alembic import op

revision = "wo009_batches"
down_revision = "wo002_wo006_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS order_batches (
            id         SERIAL PRIMARY KEY,
            store_id   INTEGER NOT NULL REFERENCES stores(id),
            title      TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at  TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_order_batches_store_id ON order_batches (store_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS order_commits (
            id              SERIAL PRIMARY KEY,
            batch_id        INTEGER NOT NULL REFERENCES order_batches(id),
            raw_text_sha256 TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_order_commits_batch_hash UNIQUE (batch_id, raw_text_sha256)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_order_commits_batch_id ON order_commits (batch_id)")

    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS batch_id INTEGER REFERENCES order_batches(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_orders_batch_id ON orders (batch_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_orders_batch_id")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS batch_id")
    op.execute("DROP INDEX IF EXISTS ix_order_commits_batch_id")
    op.execute("DROP TABLE IF EXISTS order_commits")
    op.execute("DROP INDEX IF EXISTS ix_order_batches_store_id")
    op.execute("DROP TABLE IF EXISTS order_batches")
