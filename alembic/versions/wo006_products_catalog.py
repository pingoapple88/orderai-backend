"""wo006_products_catalog — 商品型錄表 products（WO-006）。

Revision ID: wo006_products
Revises: 0004_add_cust_dealer
Create Date: 2026-07-21

用語意 revision id（非流水號），避免與未進 main 的 WO-002 之 0005 撞名。
WO-002 進 main 後會有兩個 head，屆時用 `alembic merge` 收斂（已記入回報「已知待辦」）。

契約 §2.1：id/store_id 依既有 schema 用 INTEGER（既有 stores.id 為 Integer，
契約寫的 uuid 與既有牴觸，以既有為準）。price_cents 整數分（律七）。
aliases 用 JSONB（測試庫為真 PostgreSQL；不需 with_variant sqlite）。
CREATE TABLE IF NOT EXISTS + DROP IF EXISTS：冪等，對齊本專案既有 migration 風格。
"""
from alembic import op

revision = "wo006_products"
down_revision = "0004_add_cust_dealer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id          SERIAL PRIMARY KEY,
            store_id    INTEGER NOT NULL REFERENCES stores(id),
            name        TEXT NOT NULL,
            aliases     JSONB NOT NULL DEFAULT '[]'::jsonb,
            unit        TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            is_active   BOOLEAN NOT NULL DEFAULT true,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_products_store_name UNIQUE (store_id, name)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_store_id ON products (store_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_store_id")
    op.execute("DROP TABLE IF EXISTS products")
