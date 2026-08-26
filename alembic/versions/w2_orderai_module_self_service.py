"""W2 OrderAI module self-service and Contract v1.8 event outbox.

Revision ID: w2_orderai_module_self_service
Revises: w1_team5_risk_defense
Create Date: 2026-08-25
"""
from alembic import op


revision = "w2_orderai_module_self_service"
down_revision = "w1_team5_risk_defense"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS store_key VARCHAR(64)")
    op.execute("UPDATE stores SET store_key = 'ord_' || id::text WHERE store_key IS NULL")
    op.execute("ALTER TABLE stores ADD CONSTRAINT uq_stores_store_key UNIQUE (store_key)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS module_registrations (
          id SERIAL PRIMARY KEY,
          company_id INTEGER NOT NULL REFERENCES companies(id),
          store_id INTEGER NOT NULL REFERENCES stores(id),
          module_key VARCHAR(50) NOT NULL,
          module_version VARCHAR(20) NOT NULL,
          channel VARCHAR(20) NOT NULL CHECK (channel IN ('direct', 'dealer', 'enterprise')),
          locale VARCHAR(10) NOT NULL,
          status VARCHAR(50) NOT NULL,
          idempotency_key VARCHAR(255) NOT NULL,
          created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
          CONSTRAINT uq_module_registration_idempotency UNIQUE (module_key, idempotency_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_module_registrations_company_id ON module_registrations(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_module_registrations_store_id ON module_registrations(store_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS module_registrations")
    op.execute("ALTER TABLE stores DROP CONSTRAINT IF EXISTS uq_stores_store_key")
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS store_key")
