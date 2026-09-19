"""p1_line_event_claimed_at — retain the worker claim time for manual recovery.

Revision ID: p1_line_event_claimed_at
Revises: p1_line_intake_ledger
Create Date: 2026-09-19

This migration adds operational metadata only. It neither replays events nor
creates Customer, Order, payment, inventory, delivery, or ERP records.
"""
from alembic import op
import sqlalchemy as sa


revision = "p1_line_event_claimed_at"
down_revision = "p1_line_intake_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "line_webhook_events",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("line_webhook_events", "claimed_at")
