"""0004: Option A 租戶模型 (tenants→stores) + 金額欄位改名為 *_cents

金額欄位在 v2.0 起「已是整數分」(schema.sql / models 皆 Integer 分)。
本遷移對金額只做「純欄位改名」(total_amount→total_cents 等)，值不變、不做任何
算術回填 (絕不 *100)、不保留舊欄位。派工單 §0 宣稱 DECIMAL(10,2) 為誤植，以
repo 實際 INTEGER 分為準 (Dennis 2026-07-12 裁示)。

新表 companies / dealers / customers 一律 INTEGER 自增 PK，所有 FK 皆 Integer，
與現有 stores/users/orders 的 INTEGER PK 一致 (Dennis 裁示，不用 Text 前綴)。

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. companies (可 NULL 母層，INTEGER PK) ---
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- 2. dealers (獨立表；※ 無 commission_rate，費率唯一來源在 merchcore-platform) ---
    op.create_table(
        "dealers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("code", sa.Text, nullable=False, unique=True),  # 推薦碼
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- 3. tenants → stores (純表名重命名，無資料風險) ---
    op.rename_table("tenants", "stores")
    # ※ market / industry_type 欄位保留原樣。plan 為「新增」欄位。
    op.add_column("stores", sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=True))
    op.add_column("stores", sa.Column("referred_by_dealer_id", sa.Integer, sa.ForeignKey("dealers.id"), nullable=True))
    op.add_column("stores", sa.Column("plan", sa.Text, nullable=False, server_default="lite"))
    op.add_column("stores", sa.Column("line_channel_id", sa.Text, nullable=True))
    # ※ 不建 line_channel_secret_encrypted / line_access_token_encrypted。
    #    v0 單一 channel，secret 只存在 Railway ENV，DB 不碰密鑰。

    # --- 4. customers (INTEGER PK，store_id INTEGER FK) ---
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("line_user_id", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- 5. users: tenant_id → store_id，新增 picture_url ---
    op.alter_column("users", "tenant_id", new_column_name="store_id")
    op.add_column("users", sa.Column("picture_url", sa.Text, nullable=True))
    # ※ users.line_id 全域 UNIQUE 保留不動 (scalar_one_or_none 在全域 UNIQUE 下安全)。

    # --- 6. orders: tenant_id→store_id，新增 customer_id/ai_extraction/confirmed_at，金額改名 ---
    op.alter_column("orders", "tenant_id", new_column_name="store_id")
    op.add_column("orders", sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True))
    op.add_column("orders", sa.Column("ai_extraction", postgresql.JSONB, nullable=True))
    op.add_column("orders", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    # 金額：值已是分，純改名，不動值、不 *100。
    op.alter_column("orders", "total_amount", new_column_name="total_cents")

    # --- 7. order_items: 金額改名 + 新增 unit ---
    op.add_column("order_items", sa.Column("unit", sa.Text, nullable=False, server_default="個"))
    op.alter_column("order_items", "unit_price", new_column_name="unit_price_cents")
    op.alter_column("order_items", "subtotal", new_column_name="subtotal_cents")

    # --- 8. 索引 (既有 tenant 命名的兩支改名避免重複；customers 新建；order_number 依 store 唯一) ---
    op.execute("ALTER INDEX idx_orders_tenant_id RENAME TO idx_orders_store_id")
    op.execute("ALTER INDEX idx_users_tenant_id RENAME TO idx_users_store_id")
    op.create_index("idx_customers_store_id", "customers", ["store_id"])
    op.create_index("idx_order_number_unique", "orders", ["store_id", "order_number"], unique=True)


def downgrade() -> None:
    # 反向：索引 → orders/order_items 金額改回 → 欄位/表還原。
    op.drop_index("idx_order_number_unique", table_name="orders")
    op.drop_index("idx_customers_store_id", table_name="customers")
    op.execute("ALTER INDEX idx_users_store_id RENAME TO idx_users_tenant_id")
    op.execute("ALTER INDEX idx_orders_store_id RENAME TO idx_orders_tenant_id")

    # order_items
    op.alter_column("order_items", "subtotal_cents", new_column_name="subtotal")
    op.alter_column("order_items", "unit_price_cents", new_column_name="unit_price")
    op.drop_column("order_items", "unit")

    # orders
    op.alter_column("orders", "total_cents", new_column_name="total_amount")
    op.drop_column("orders", "confirmed_at")
    op.drop_column("orders", "ai_extraction")
    op.drop_column("orders", "customer_id")
    op.alter_column("orders", "store_id", new_column_name="tenant_id")

    # users
    op.drop_column("users", "picture_url")
    op.alter_column("users", "store_id", new_column_name="tenant_id")

    # customers
    op.drop_table("customers")

    # stores → tenants
    op.drop_column("stores", "line_channel_id")
    op.drop_column("stores", "plan")
    op.drop_column("stores", "referred_by_dealer_id")
    op.drop_column("stores", "company_id")
    op.rename_table("stores", "tenants")

    # dealers / companies
    op.drop_table("dealers")
    op.drop_table("companies")
