"""T5 OrderAI self-service subscriptions and invoice-status records.

Revision ID: w2_orderai_subscriptions
Revises: w2_orderai_module_self_service
Create Date: 2026-08-28
"""
from alembic import op


revision = "w2_orderai_subscriptions"
down_revision = "w2_orderai_module_self_service"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_records (
          id SERIAL PRIMARY KEY,
          company_id INTEGER NOT NULL REFERENCES companies(id),
          store_id INTEGER NOT NULL REFERENCES stores(id),
          user_id INTEGER NOT NULL REFERENCES users(id),
          plan_id INTEGER NOT NULL REFERENCES plans(id),
          channel VARCHAR(20) NOT NULL CHECK (channel IN ('direct', 'dealer', 'enterprise')),
          status VARCHAR(50) NOT NULL DEFAULT 'pending_payment',
          entitlement_status VARCHAR(50) NOT NULL DEFAULT 'pending_activation',
          payment_reference VARCHAR(255),
          idempotency_key VARCHAR(64) NOT NULL,
          current_period_end TIMESTAMPTZ,
          canceled_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_subscription_company_idempotency UNIQUE (company_id, idempotency_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscription_records_store_id ON subscription_records(store_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscription_records_user_id ON subscription_records(user_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_records (
          id SERIAL PRIMARY KEY,
          company_id INTEGER NOT NULL REFERENCES companies(id),
          store_id INTEGER NOT NULL REFERENCES stores(id),
          user_id INTEGER NOT NULL REFERENCES users(id),
          subscription_id INTEGER NOT NULL REFERENCES subscription_records(id),
          billing_record_id INTEGER REFERENCES billing_records(id) ON DELETE SET NULL,
          amount_minor INTEGER NOT NULL,
          currency VARCHAR(3) NOT NULL,
          status VARCHAR(50) NOT NULL DEFAULT 'pending',
          provider_reference VARCHAR(255),
          idempotency_key VARCHAR(64) NOT NULL,
          issued_at TIMESTAMPTZ,
          due_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_invoice_company_idempotency UNIQUE (company_id, idempotency_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_invoice_records_subscription_id ON invoice_records(subscription_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_invoice_records_store_id ON invoice_records(store_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS invoice_records")
    op.execute("DROP TABLE IF EXISTS subscription_records")
