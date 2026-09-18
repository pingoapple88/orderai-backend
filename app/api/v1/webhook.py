"""LINE Webhook: signature verification, mandatory P1 ledger intake, and queueing.

A signed request is never routed to the legacy direct Customer/Order workflow.
It must be recorded in the existing P1 event ledger before queueing, or the
endpoint fails closed.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import verify_line_signature
from app.providers import get_queue
from app.services import p1_intake_service

router = APIRouter()
settings = get_settings()


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
        store = p1_intake_service.resolve_p1_store(db)
        inserted = p1_intake_service.record_line_events(db, payload, store)
    except p1_intake_service.P1IntakeConfigurationError:
        db.rollback()
        return Response(status_code=503)
    finally:
        db.close()

    # Redeliveries are ACKed but do not enqueue another worker job.
    if not inserted:
        return Response(status_code=200)

    get_queue().enqueue(payload)
    return Response(status_code=200)
