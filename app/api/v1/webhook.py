"""LINE webhook: signature verification, mandatory P1 ledger intake, and queueing.

A signed request is never routed to the legacy direct Customer/Order workflow.
It must be bound to the configured LINE destination, recorded in the existing P1
event ledger, and queued only after all fail-closed gates have passed.
"""
from __future__ import annotations

import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import verify_line_signature
from app.models import LineWebhookEvent
from app.providers import get_queue
from app.services import p1_intake_service

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


def _destination_matches(payload: dict[str, Any]) -> bool:
    """Require an exact, deployment-provided Bot destination before any DB write.

    The value is not a secret, but exact comparison prevents a signed event for a
    different official account from being silently assigned to DEFAULT_STORE_ID.
    """
    expected = settings.p1_line_destination.strip()
    destination = payload.get("destination")
    return bool(expected and isinstance(destination, str) and hmac.compare_digest(destination, expected))


def _record_and_enqueue_signed_events(payload: dict[str, Any]) -> Response:
    """Run blocking SQLAlchemy and queue work in FastAPI's thread pool.

    Each signed event is queued at most once per HTTP payload. Durable ledger
    deduplication and worker claim locking remain the authoritative protections
    across retries, concurrent requests, and process restarts.
    """
    db = SessionLocal()
    try:
        try:
            store = p1_intake_service.resolve_p1_store(db)
            inserted = p1_intake_service.record_line_events(db, payload, store)
        except p1_intake_service.P1IntakeConfigurationError:
            db.rollback()
            return Response(status_code=503)

        # Redeliveries already accepted or processed are ACKed without another job.
        if not inserted:
            return Response(status_code=200)

        event_ids = {
            webhook_event_id: ledger_id
            for ledger_id, webhook_event_id in db.execute(
                select(LineWebhookEvent.id, LineWebhookEvent.webhook_event_id)
                .where(LineWebhookEvent.id.in_(inserted))
            )
        }
        pending: list[tuple[dict[str, Any], int]] = []
        seen_event_ids: set[str] = set()
        for event in payload.get("events", []):
            if not isinstance(event, dict):
                continue
            event_id = event.get("webhookEventId")
            if not isinstance(event_id, str) or event_id in seen_event_ids or event_id not in event_ids:
                continue
            seen_event_ids.add(event_id)
            pending.append((event, event_ids[event_id]))

        queue = get_queue()
        for index, (event, _ledger_id) in enumerate(pending):
            try:
                queue.enqueue({**payload, "events": [event]})
            except Exception as exc:  # noqa: BLE001 - only the unqueued suffix becomes replayable.
                p1_intake_service.mark_enqueue_failed(
                    db,
                    store_id=store.id,
                    event_ids=[pending_id for _, pending_id in pending[index:]],
                )
                logger.error("P1 queue enqueue failed exception=%s", exc.__class__.__name__)
                return Response(status_code=503)
        return Response(status_code=200)
    finally:
        db.close()


@router.post("/line")
async def line_webhook(request: Request) -> Response:
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_line_signature(body, signature, settings.line_messaging_channel_secret):
        return Response(status_code=401)

    try:
        payload = json.loads(body)
    except Exception:
        return Response(status_code=400)
    if not isinstance(payload, dict):
        return Response(status_code=400)

    # Every signed inbound event must enter the existing encrypted/HMAC P1 ledger
    # before queueing. Disabling, incompletely configuring, or misbinding P1 is
    # fail-closed; it never restores the removed legacy direct-order behavior.
    if not settings.p1_intake_enabled or not _destination_matches(payload):
        return Response(status_code=503)

    return await run_in_threadpool(_record_and_enqueue_signed_events, payload)
