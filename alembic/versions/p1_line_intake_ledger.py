"""p1_line_intake_ledger — 青泉谷受控 LINE 事件帳本與待確認草稿。

Revision ID: p1_line_intake_ledger
Revises: m1_inv_01
Create Date: 2026-09-16

本遷移不建立付款、庫存保留、扣庫、出貨或開票資料。所有可辨識草稿內容
僅存在程式層加密欄位；webhook 原始 body 與附件內容均不保存。
"""
from alembic import op


revision = "p1_line_intake_ledger"
down_revision = "m1_inv_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS line_webhook_events (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            store_id INTEGER NOT NULL REFERENCES stores(id),
            channel VARCHAR(30) NOT NULL DEFAULT 'line',
            webhook_event_id TEXT NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            message_type VARCHAR(50),
            message_id_hmac VARCHAR(64),
            source_user_hmac VARCHAR(64),
            occurred_at TIMESTAMPTZ,
            status VARCHAR(30) NOT NULL DEFAULT 'queued',
            error_code VARCHAR(100),
            processed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_line_webhook_events_store_channel_event UNIQUE (store_id, channel, webhook_event_id),
            CONSTRAINT ck_line_webhook_events_status CHECK (status IN ('queued', 'processing', 'processed', 'failed'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_line_webhook_events_company_id ON line_webhook_events (company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_line_webhook_events_store_id ON line_webhook_events (store_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS intake_conversations (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            store_id INTEGER NOT NULL REFERENCES stores(id),
            source_event_id INTEGER NOT NULL UNIQUE REFERENCES line_webhook_events(id),
            source_kind VARCHAR(30) NOT NULL,
            source_user_hmac VARCHAR(64),
            state VARCHAR(50) NOT NULL,
            state_version INTEGER NOT NULL DEFAULT 1,
            reason_codes JSONB,
            draft_ciphertext TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_intake_conversations_state CHECK (
                state IN ('needs_human_review', 'awaiting_customer_confirmation', 'awaiting_erp_delivery', 'closed')
            )
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_conversations_company_id ON intake_conversations (company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_conversations_store_id ON intake_conversations (store_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS attachment_drafts (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            store_id INTEGER NOT NULL REFERENCES stores(id),
            conversation_id INTEGER NOT NULL REFERENCES intake_conversations(id) ON DELETE CASCADE,
            message_id_hmac VARCHAR(64),
            media_type VARCHAR(30) NOT NULL,
            content_sha256 VARCHAR(64),
            restricted_reference TEXT,
            status VARCHAR(50) NOT NULL DEFAULT 'needs_text_confirmation',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_attachment_drafts_conversation_message UNIQUE (conversation_id, message_id_hmac),
            CONSTRAINT ck_attachment_drafts_media_type CHECK (media_type IN ('image', 'audio', 'file')),
            CONSTRAINT ck_attachment_drafts_status CHECK (status IN ('needs_text_confirmation', 'needs_human_review', 'withdrawn'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_attachment_drafts_company_id ON attachment_drafts (company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attachment_drafts_store_id ON attachment_drafts (store_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attachment_drafts_conversation_id ON attachment_drafts (conversation_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS erp_delivery_outbox (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            store_id INTEGER NOT NULL REFERENCES stores(id),
            conversation_id INTEGER NOT NULL REFERENCES intake_conversations(id) ON DELETE CASCADE,
            delivery_type VARCHAR(50) NOT NULL DEFAULT 'pending_customer_and_order',
            idempotency_key VARCHAR(255) NOT NULL,
            payload_ciphertext TEXT NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'blocked',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error_code VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_erp_delivery_outbox_company_idempotency UNIQUE (company_id, idempotency_key),
            CONSTRAINT ck_erp_delivery_outbox_status CHECK (status IN ('blocked', 'queued', 'delivered', 'failed'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_erp_delivery_outbox_company_id ON erp_delivery_outbox (company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_erp_delivery_outbox_store_id ON erp_delivery_outbox (store_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_erp_delivery_outbox_conversation_id ON erp_delivery_outbox (conversation_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_erp_delivery_outbox_conversation_id")
    op.execute("DROP INDEX IF EXISTS ix_erp_delivery_outbox_store_id")
    op.execute("DROP INDEX IF EXISTS ix_erp_delivery_outbox_company_id")
    op.execute("DROP TABLE IF EXISTS erp_delivery_outbox")
    op.execute("DROP INDEX IF EXISTS ix_attachment_drafts_conversation_id")
    op.execute("DROP INDEX IF EXISTS ix_attachment_drafts_store_id")
    op.execute("DROP INDEX IF EXISTS ix_attachment_drafts_company_id")
    op.execute("DROP TABLE IF EXISTS attachment_drafts")
    op.execute("DROP INDEX IF EXISTS ix_intake_conversations_store_id")
    op.execute("DROP INDEX IF EXISTS ix_intake_conversations_company_id")
    op.execute("DROP TABLE IF EXISTS intake_conversations")
    op.execute("DROP INDEX IF EXISTS ix_line_webhook_events_store_id")
    op.execute("DROP INDEX IF EXISTS ix_line_webhook_events_company_id")
    op.execute("DROP TABLE IF EXISTS line_webhook_events")
