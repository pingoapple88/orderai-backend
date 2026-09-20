"""Fail-closed synthetic LINE webhook acceptance for the Qingquangu P1 UAT tenant.

The caller posts exactly one synthetic, unsupported LINE message to the OrderAI
webhook and immediately replays the identical signed body.  It never calls the
LINE platform, never performs review or ERP dispatch, and never creates data
directly: all writes are made by the target OrderAI webhook/worker path.

This module is intentionally usable only from a controlled shell that provides
all configuration and credentials through environment variables.  Its JSON
result contains hashes, statuses, and aggregate counts only.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session



_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_KNOWN_PRODUCTION_HOSTS = {
    "orderai.merchcore.ai",
    "app.orderai.merchcore.ai",
    "api.orderai.merchcore.ai",
}
_SYNTHETIC_EVENT_ID = "qingquan-p1-uat-webhook-human-review-v1"
_UAT_ENVIRONMENT = "uat"
_UAT_MARKER = "qingquan-p1-uat"
_SYNTHETIC_COMPANY_NAME = "青泉谷 P1 UAT 合成公司"
_SYNTHETIC_STORE_KEY = "qingquan-p1-uat-orderai-store"


class P1WebhookAcceptanceBlocked(RuntimeError):
    """A target, baseline, or result violates the controlled acceptance boundary."""


class _HttpResponse(Protocol):
    status_code: int


@dataclass(frozen=True)
class _Target:
    api_base_url: str
    endpoint_url: str
    database_host: str


@dataclass(frozen=True)
class _SyntheticScope:
    company_id: int
    store_id: int


def _environment_value(name: str) -> str:
    """Read only process environment; never fall back to a config file or default."""
    return os.environ.get(name, "").strip()


def _blocked(code: str) -> None:
    raise P1WebhookAcceptanceBlocked(code)


def _host_is_production(host: str) -> bool:
    if host in _KNOWN_PRODUCTION_HOSTS:
        return True
    labels = [label for label in host.split(".") if label]
    return any(
        token in label
        for label in labels
        for token in {"prod", "production", "live"}
    )


def _parse_api_target(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if (
        not value
        or parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        _blocked("P1_WEBHOOK_ACCEPTANCE_API_URL_INVALID")
    if _host_is_production(host):
        _blocked("P1_WEBHOOK_ACCEPTANCE_PRODUCTION_HOST_REJECTED")
    if parsed.scheme != "https" and host not in _LOCAL_HOSTS:
        _blocked("P1_WEBHOOK_ACCEPTANCE_HTTPS_REQUIRED")
    return value.rstrip("/"), host


def _parse_database_host(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if not value or not host or parsed.username is None:
        _blocked("P1_WEBHOOK_ACCEPTANCE_DATABASE_URL_INVALID")
    if _host_is_production(host):
        _blocked("P1_WEBHOOK_ACCEPTANCE_PRODUCTION_DATABASE_REJECTED")
    return host


def _allowed_hosts(value: str) -> set[str]:
    hosts = {host.strip().lower() for host in value.split(",") if host.strip()}
    if not hosts or any("*" in host or "://" in host or "/" in host for host in hosts):
        _blocked("P1_WEBHOOK_ACCEPTANCE_ALLOWED_HOSTS_INVALID")
    if any(_host_is_production(host) for host in hosts):
        _blocked("P1_WEBHOOK_ACCEPTANCE_PRODUCTION_HOST_REJECTED")
    return hosts


def _validated_target() -> tuple[_Target, str]:
    """Validate UAT identity, API allowlist, and DB scope before any API call."""
    if _environment_value("ENVIRONMENT").lower() in {"production", "prod", "live"}:
        _blocked("P1_WEBHOOK_ACCEPTANCE_PRODUCTION_ENVIRONMENT_REJECTED")
    if _environment_value("ENVIRONMENT").lower() != _UAT_ENVIRONMENT:
        _blocked("P1_WEBHOOK_ACCEPTANCE_ENVIRONMENT_NOT_UAT")
    if _environment_value("P1_UAT_ENVIRONMENT_MARKER") != _UAT_MARKER:
        _blocked("P1_WEBHOOK_ACCEPTANCE_UAT_MARKER_INVALID")

    api_base_url, api_host = _parse_api_target(
        _environment_value("P1_WEBHOOK_ACCEPTANCE_API_BASE_URL")
    )
    if api_host not in _allowed_hosts(_environment_value("P1_WEBHOOK_ACCEPTANCE_ALLOWED_HOSTS")):
        _blocked("P1_WEBHOOK_ACCEPTANCE_API_HOST_NOT_ALLOWED")

    database_host = _parse_database_host(_environment_value("DATABASE_URL"))
    configured_database_host = _environment_value("P1_WEBHOOK_ACCEPTANCE_DATABASE_HOST").lower()
    if not configured_database_host or database_host != configured_database_host:
        _blocked("P1_WEBHOOK_ACCEPTANCE_DATABASE_HOST_INVALID")
    if _host_is_production(configured_database_host):
        _blocked("P1_WEBHOOK_ACCEPTANCE_PRODUCTION_DATABASE_REJECTED")

    # Local development and remote UAT are deliberately separate.  A remote
    # endpoint must pair with an explicitly named UAT internal database; a
    # localhost endpoint may only pair with localhost database access.
    api_is_local = api_host in _LOCAL_HOSTS
    database_is_local = database_host in _LOCAL_HOSTS
    if api_is_local != database_is_local:
        _blocked("P1_WEBHOOK_ACCEPTANCE_API_DATABASE_SCOPE_MISMATCH")
    if not api_is_local:
        if configured_database_host != _environment_value("P1_UAT_DATABASE_HOST").lower():
            _blocked("P1_WEBHOOK_ACCEPTANCE_UAT_DATABASE_HOST_INVALID")
        if not configured_database_host.endswith(".railway.internal"):
            _blocked("P1_WEBHOOK_ACCEPTANCE_UAT_DATABASE_NOT_ISOLATED")

    # The signing secret has no CLI fallback and is neither returned nor logged.
    line_secret = _environment_value("LINE_MESSAGING_CHANNEL_SECRET")
    if not line_secret:
        _blocked("P1_WEBHOOK_ACCEPTANCE_LINE_SECRET_MISSING")

    return (
        _Target(
            api_base_url=api_base_url,
            endpoint_url=f"{api_base_url}/api/v1/webhooks/line",
            database_host=database_host,
        ),
        line_secret,
    )


def _synthetic_scope(db: Session) -> _SyntheticScope:
    """Resolve only the pre-existing, precisely named Qingquangu UAT tenant."""
    from app.models import Company, Store

    row = db.execute(
        select(Store.id, Store.company_id)
        .join(Company, Company.id == Store.company_id)
        .where(
            Store.store_key == _SYNTHETIC_STORE_KEY,
            Company.name == _SYNTHETIC_COMPANY_NAME,
        )
    ).one_or_none()
    if row is None or row.company_id is None:
        _blocked("P1_WEBHOOK_ACCEPTANCE_SYNTHETIC_SCOPE_NOT_FOUND")
    return _SyntheticScope(company_id=int(row.company_id), store_id=int(row.id))


def _count(db: Session, model: Any, store_id: int) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(model.store_id == store_id)) or 0)


def _side_effect_counts(db: Session, store_id: int) -> dict[str, int]:
    """Return only scoped aggregates; this service models no shipment/invoice ledger."""
    from app.models import BillingRecord, Customer, InventoryInquiry, Order

    return {
        "customer": _count(db, Customer, store_id),
        "order": _count(db, Order, store_id),
        "payment": _count(db, BillingRecord, store_id),
        # InventoryInquiry is the only local inventory-related model; it is
        # manual-only and is not a reservation or stock decrement.
        "inventory": _count(db, InventoryInquiry, store_id),
        "shipment": 0,
        "invoice": 0,
    }


def _assert_safe_baseline(db: Session, scope: _SyntheticScope) -> None:
    """Allow only a clean scope or this tool's already-complete fixed replay case."""
    from app.models import IntakeConversation, LineWebhookEvent

    if any(_side_effect_counts(db, scope.store_id).values()):
        _blocked("P1_WEBHOOK_ACCEPTANCE_BASELINE_NOT_EMPTY")

    line_event_count = int(db.scalar(
        select(func.count()).select_from(LineWebhookEvent).where(
            LineWebhookEvent.store_id == scope.store_id,
            LineWebhookEvent.channel == "line",
        )
    ) or 0)
    scoped_case_count = int(db.scalar(
        select(func.count()).select_from(IntakeConversation)
        .join(LineWebhookEvent, LineWebhookEvent.id == IntakeConversation.source_event_id)
        .where(
            IntakeConversation.store_id == scope.store_id,
            LineWebhookEvent.channel == "line",
        )
    ) or 0)
    event_count, event_status, case_count, case_state = _event_snapshot(
        db, scope, _SYNTHETIC_EVENT_ID
    )
    if event_count == 0 and line_event_count == 0 and scoped_case_count == 0:
        return
    if (
        event_count == 1
        and line_event_count == 1
        and scoped_case_count == 1
        and event_status == "processed"
        and case_count == 1
        and case_state == "needs_human_review"
    ):
        return
    _blocked("P1_WEBHOOK_ACCEPTANCE_BASELINE_NOT_CLEAN")


def _signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _payload(event_id: str) -> bytes:
    """Use an unsupported sticker: no LLM, media download, reply, review, or ERP path."""
    payload = {
        "destination": "UAT_QINGQUAN_P1_ORDERAI_DESTINATION",
        "events": [
            {
                "type": "message",
                "mode": "active",
                "timestamp": 1_700_000_000_000,
                "source": {"type": "user", "userId": "UAT_QINGQUAN_P1_SYNTHETIC_USER"},
                "webhookEventId": event_id,
                "deliveryContext": {"isRedelivery": False},
                "message": {"id": f"synthetic-{event_id}", "type": "sticker", "packageId": "1", "stickerId": "1"},
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _event_snapshot(db: Session, scope: _SyntheticScope, event_id: str) -> tuple[int, str | None, int, str | None]:
    from app.models import IntakeConversation, LineWebhookEvent

    events = list(
        db.execute(
            select(LineWebhookEvent).where(
                LineWebhookEvent.company_id == scope.company_id,
                LineWebhookEvent.store_id == scope.store_id,
                LineWebhookEvent.channel == "line",
                LineWebhookEvent.webhook_event_id == event_id,
            )
        ).scalars()
    )
    if len(events) != 1:
        return len(events), None, 0, None
    event = events[0]
    cases = list(
        db.execute(
            select(IntakeConversation).where(
                IntakeConversation.company_id == scope.company_id,
                IntakeConversation.store_id == scope.store_id,
                IntakeConversation.source_event_id == event.id,
            )
        ).scalars()
    )
    return 1, event.status, len(cases), cases[0].state if len(cases) == 1 else None


def _wait_for_human_review(
    db: Session,
    scope: _SyntheticScope,
    event_id: str,
    timeout_seconds: float,
    sleep: Callable[[float], None],
) -> tuple[int, str | None, int, str | None]:
    deadline = time.monotonic() + timeout_seconds
    snapshot = _event_snapshot(db, scope, event_id)
    while time.monotonic() < deadline:
        if snapshot == (1, "processed", 1, "needs_human_review"):
            return snapshot
        sleep(0.1)
        db.expire_all()
        snapshot = _event_snapshot(db, scope, event_id)
    if snapshot[0] != 1:
        _blocked("P1_WEBHOOK_ACCEPTANCE_LEDGER_NOT_EXACTLY_ONCE")
    if snapshot[1] != "processed":
        _blocked("P1_WEBHOOK_ACCEPTANCE_LEDGER_NOT_PROCESSED")
    if snapshot[2] != 1:
        _blocked("P1_WEBHOOK_ACCEPTANCE_CASE_NOT_EXACTLY_ONCE")
    _blocked("P1_WEBHOOK_ACCEPTANCE_CASE_NOT_HUMAN_REVIEW")
    raise AssertionError("unreachable")


def run_p1_webhook_acceptance(
    *,
    timeout_seconds: float = 15.0,
    session_factory: Callable[[], Session] | None = None,
    post: Callable[..., _HttpResponse] = httpx.post,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run one signed webhook plus replay and return de-identified JSON evidence.

    The direct database access is read-only and is required solely to verify the
    ledger, case state, and zero local side effects.  The only write is the two
    HTTP requests to the explicitly allowlisted OrderAI API.
    """
    if not 0 < timeout_seconds <= 120:
        _blocked("P1_WEBHOOK_ACCEPTANCE_TIMEOUT_INVALID")
    target, line_secret = _validated_target()
    if session_factory is None:
        # All application configuration/model imports remain deferred until the
        # environment, marker, host, allowlist, and secret guards have passed.
        from app.core.database import SessionLocal
        session_factory = SessionLocal
    db = session_factory()
    try:
        scope = _synthetic_scope(db)
        _assert_safe_baseline(db, scope)

        event_id = _SYNTHETIC_EVENT_ID
        body = _payload(event_id)
        headers = {
            "Content-Type": "application/json",
            "X-Line-Signature": _signature(body, line_secret),
            "User-Agent": "orderai-p1-synthetic-acceptance",
        }
        # This posts to OrderAI only.  The payload has no reply token and its
        # unsupported message type cannot reach LLM, LINE notification, review,
        # ERP dispatch, payment, inventory, shipment, or invoice code paths.
        try:
            initial = post(target.endpoint_url, content=body, headers=headers, timeout=10.0)
            replay = post(target.endpoint_url, content=body, headers=headers, timeout=10.0)
        except httpx.HTTPError as exc:
            raise P1WebhookAcceptanceBlocked("P1_WEBHOOK_ACCEPTANCE_HTTP_TRANSPORT_FAILED") from exc
        if initial.status_code != 200:
            _blocked("P1_WEBHOOK_ACCEPTANCE_INITIAL_HTTP_UNEXPECTED")
        if replay.status_code != 200:
            _blocked("P1_WEBHOOK_ACCEPTANCE_REPLAY_HTTP_UNEXPECTED")

        ledger_count, ledger_status, case_count, case_state = _wait_for_human_review(
            db, scope, event_id, timeout_seconds, sleep
        )
        side_effects = _side_effect_counts(db, scope.store_id)
        if any(side_effects.values()):
            _blocked("P1_WEBHOOK_ACCEPTANCE_SIDE_EFFECT_DETECTED")

        return {
            "action": "p1_webhook_acceptance",
            "synthetic_only": True,
            "event_id_sha256": hashlib.sha256(event_id.encode("utf-8")).hexdigest(),
            "http": {"initial_status": initial.status_code, "replay_status": replay.status_code},
            "event_ledger": {"count": ledger_count, "status": ledger_status},
            "case": {"count": case_count, "state": case_state},
            "side_effect_counts": side_effects,
            "side_effect_scope": {
                "customer": "customers",
                "order": "orders",
                "payment": "billing_records",
                "inventory": "inventory_inquiries (manual inquiry only; no reservation/decrement ledger exists)",
                "shipment": "not_modelled_by_this_service",
                "invoice": "not_modelled_by_this_service",
            },
            "replay": {
                "duplicate_ledger_entries": ledger_count - 1,
                "duplicate_cases": case_count - 1,
                "not_duplicated": ledger_count == 1 and case_count == 1,
            },
            "passed": True,
        }
    finally:
        db.close()


def safe_json_evidence(summary: dict[str, Any]) -> str:
    """Centralized output path; summaries intentionally contain no secret or raw event."""
    return json.dumps(summary, ensure_ascii=False, sort_keys=True)


__all__ = [
    "P1WebhookAcceptanceBlocked",
    "run_p1_webhook_acceptance",
    "safe_json_evidence",
]
