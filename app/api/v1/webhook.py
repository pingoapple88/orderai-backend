"""LINE Webhook: signature verification, mandatory P1 ledger intake, and queueing.

A signed request is never routed to the legacy direct Customer/Order workflow.
It must be recorded in the existing P1 event ledger before queueing, or the
endpoint fails closed.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request, Response
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

    # Every signed inbound event must enter the existing encrypted/HMAC P1 ledger
    # before queueing. Disabling or incompletely configuring P1 is fail-closed;
    # it never restores the removed legacy direct-order behavior.
    if not settings.p1_intake_enabled:
        return Response(status_code=503)

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

        # One event per job contains partial enqueue failures: an outage after
        # event N leaves only the unqueued suffix recoverable by an official LINE
        # redelivery. Already queued events are not marked failed or duplicated.
        event_ids = {
            webhook_event_id: ledger_id
            for ledger_id, webhook_event_id in db.execute(
                select(LineWebhookEvent.id, LineWebhookEvent.webhook_event_id)
                .where(LineWebhookEvent.id.in_(inserted))
            )
        }
        pending = [
            (event, event_ids[event_id])
            for event in payload.get("events", [])
            if isinstance((event_id := event.get("webhookEventId")), str) and event_id in event_ids
        ]
        queue = get_queue()
        for index, (event, event_id) in enumerate(pending):
            try:
                queue.enqueue({**payload, "events": [event]})
            except Exception:  # noqa: BLE001 - preserve only the unqueued suffix for official redelivery.
                p1_intake_service.mark_enqueue_failed(
                    db,
                    store_id=store.id,
                    event_ids=[pending_id for _, pending_id in pending[index:]],
                )
                logger.exception("P1 queue enqueue failed; unqueued signed events remain recoverable")
                return Response(status_code=503)
        return Response(status_code=200)
    finally:
        db.close()
