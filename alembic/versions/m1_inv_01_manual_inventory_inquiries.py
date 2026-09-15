"""m1_inv_01_manual_inventory_inquiries — 人工庫存確認工作項。

Revision ID: m1_inv_01
Revises: w2_orderai_module_self_service
Create Date: 2026-09-15

只保存詢問與人工確認結果。此遷移不建立庫存餘額、保留、扣庫、付款或出貨資料。
"""
from alembic import op


revision = "m1_inv_01"
down_revision = "w2_orderai_module_self_service"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_inquiries (
            id                  SERIAL PRIMARY KEY,
            store_id            INTEGER NOT NULL REFERENCES stores(id),
            product_id          INTEGER REFERENCES products(id) ON DELETE SET NULL,
            customer_id         INTEGER REFERENCES customers(id) ON DELETE SET NULL,
            requester_name      TEXT,
            requested_product_name TEXT NOT NULL,
            requested_quantity INTEGER,
            requested_unit      TEXT,
            status              VARCHAR(30) NOT NULL DEFAULT 'pending_review',
            decision_note       TEXT,
            reviewed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at         TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_inventory_inquiries_status
                CHECK (status IN ('pending_review', 'available', 'unavailable')),
            CONSTRAINT ck_inventory_inquiries_quantity_positive
                CHECK (requested_quantity IS NULL OR requested_quantity > 0)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_inventory_inquiries_store_id ON inventory_inquiries (store_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inventory_inquiries_product_id ON inventory_inquiries (product_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inventory_inquiries_customer_id ON inventory_inquiries (customer_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inventory_inquiries_store_status_created "
        "ON inventory_inquiries (store_id, status, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_inventory_inquiries_store_status_created")
    op.execute("DROP INDEX IF EXISTS ix_inventory_inquiries_customer_id")
    op.execute("DROP INDEX IF EXISTS ix_inventory_inquiries_product_id")
    op.execute("DROP INDEX IF EXISTS ix_inventory_inquiries_store_id")
    op.execute("DROP TABLE IF EXISTS inventory_inquiries")
