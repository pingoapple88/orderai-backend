"""LINE inbound worker: P1 event-ledger intake and human review only.

Every inbound LINE event must first have been signature-verified and claimed from
the existing P1 ``LineWebhookEvent`` ledger. This worker only creates the
existing P1 ``needs_human_review`` case (and, where eligible, a *blocked* ERP
outbox draft). It never creates a local Customer or Order, and it never
confirms a sale or dispatches ERP delivery.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Dict, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services import order_risk_service, p1_intake_service, product_service

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_text_from_event(event: Dict[str, Any]) -> Optional[str]:
    """Return text content only; non-text events remain controlled P1 cases."""
    message = event.get("message", {})
    if message.get("type") == "text":
        return message.get("text")
    return None


async def _safe_attachment_followup(notif, *, reply_token: Optional[str], user_id: Optional[str]) -> None:
    """Do not pretend to request clarification without an official configured channel."""
    if not (
        settings.p1_attachment_followup_enabled
        and settings.line_messaging_access_token
        and reply_token
        and user_id
    ):
        return
    try:
        await notif.send_message(
            to=user_id,
            reply_token=reply_token,
            text="已收到附件。為避免辨識錯誤，請直接以文字提供訂購人、商品、數量、需要時間與特別要求。",
        )
    except Exception:  # noqa: BLE001 - Retain the review case; do not retry an external notification.
        logger.warning("P1 attachment follow-up unavailable; retained for human review")


async def _process_p1_event(db: Session, event: Dict[str, Any], llm, notif) -> None:
    """Create only an existing P1 human-review case for a claimed ledger event."""
    line_event_id = event.get("webhookEventId")
    if not isinstance(line_event_id, str) or not line_event_id:
        logger.warning("LINE event missing webhookEventId; fail closed")
        return
    try:
        store = p1_intake_service.resolve_p1_store(db)
    except p1_intake_service.P1IntakeConfigurationError as exc:
        logger.error("P1 intake store scope unavailable: %s", exc)
        return
    source_event = p1_intake_service.claim_event(db, store_id=store.id, webhook_event_id=line_event_id)
    if source_event is None:
        # Events are claimed only from the signed, deduplicated P1 ledger.
        logger.info(
            "LINE event is absent from or already claimed by P1 ledger: event_id_sha256=%s",
            hashlib.sha256(line_event_id.encode("utf-8")).hexdigest(),
        )
        return

    message = event.get("message") or {}
    message_type = message.get("type")
    source = event.get("source") or {}
    source_user_id = source.get("userId")
    reply_token = event.get("replyToken")
    try:
        if message_type in {"image", "audio", "file"}:
            p1_intake_service.create_attachment_case(
                db, store=store, source_event=source_event, media_type=message_type
            )
            await _safe_attachment_followup(notif, reply_token=reply_token, user_id=source_user_id)
            p1_intake_service.finish_event(db, source_event, store_id=store.id)
            return

        text = _get_text_from_event(event)
        if not text:
            # Stickers, locations, and other unsupported events never become orders.
            p1_intake_service.create_text_case(
                db,
                store=store,
                source_event=source_event,
                source_text="",
                source_user_id=source_user_id,
                result=type(
                    "EmptyExtraction",
                    (),
                    {
                        "items": [],
                        "customer_name": None,
                        "customer_phone": None,
                        "confidence_score": 0.0,
                        "provider_name": "",
                        "raw": {},
                    },
                )(),
                decision_status="needs_review",
                decision_reasons=["unsupported_message_type"],
            )
            p1_intake_service.finish_event(db, source_event, store_id=store.id)
            return

        try:
            result = await llm.extract_order(text=text, industry_type=store.industry_type or "ecom")
        except Exception as exc:  # noqa: BLE001 - External parsing failure stays human review.
            reason = getattr(exc, "reason_code", None) or (
                "provider_timeout"
                if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError))
                else "provider_error"
            )
            p1_intake_service.create_text_case(
                db,
                store=store,
                source_event=source_event,
                source_text=text,
                source_user_id=source_user_id,
                result=type(
                    "EmptyExtraction",
                    (),
                    {
                        "items": [],
                        "customer_name": None,
                        "customer_phone": None,
                        "confidence_score": 0.0,
                        "provider_name": "",
                        "raw": {},
                    },
                )(),
                decision_status="needs_review",
                decision_reasons=[reason],
            )
            p1_intake_service.finish_event(db, source_event, store_id=store.id)
            return

        priced = product_service.price_extracted_items(db, store.id, result.items)
        decision = order_risk_service.evaluate_order_extraction(
            db,
            extraction=result,
            priced_items=priced,
            default_threshold=settings.ai_confidence_threshold,
        )
        p1_intake_service.create_text_case(
            db,
            store=store,
            source_event=source_event,
            source_text=text,
            source_user_id=source_user_id,
            result=result,
            decision_status=decision.status,
            decision_reasons=decision.reasons,
        )
        p1_intake_service.finish_event(db, source_event, store_id=store.id)
    except p1_intake_service.P1IntakeConfigurationError as exc:
        db.rollback()
        source_event = db.get(type(source_event), source_event.id)
        if source_event is not None:
            p1_intake_service.finish_event(
                db, source_event, store_id=store.id, error_code=str(exc)
            )
        logger.error("P1 intake failed closed: %s", exc)
    except Exception:
        db.rollback()
        source_event = db.get(type(source_event), source_event.id)
        if source_event is not None:
            p1_intake_service.finish_event(
                db,
                source_event,
                store_id=store.id,
                error_code="P1_INTAKE_PROCESSING_FAILED",
            )
        logger.error("P1 intake processing failed; retained for human review")


async def _process_one_event(db: Session, event: Dict[str, Any], llm, notif) -> None:
    """All inbound LINE events follow the mandatory P1 ledger and review path."""
    if not settings.p1_intake_enabled:
        logger.error("P1 intake is disabled; queued LINE event remains fail closed")
        return
    await _process_p1_event(db, event, llm, notif)


async def process_webhook_event(payload: Dict[str, Any], db: Optional[Session] = None) -> None:
    """Process a queued payload only from its existing signed P1 ledger entries.

    ``db`` is injectable for PostgreSQL-backed focused tests; production workers
    use ``SessionLocal``. The webhook route verifies the LINE signature and
    records P1 events before queueing this function.
    """
    from app.providers import get_llm_provider, get_notification_provider

    llm = get_llm_provider()
    notif = get_notification_provider()

    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        for event in payload.get("events", []):
            await _process_one_event(db, event, llm, notif)
    finally:
        if own_session:
            db.close()


def run_worker(payload: Dict[str, Any]) -> None:
    """Synchronous RQ entry point for the mandatory P1 intake worker."""
    asyncio.run(process_webhook_event(payload))
