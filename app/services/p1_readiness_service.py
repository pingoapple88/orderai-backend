"""Store-scoped, read-only P1 operational readiness checks.

This service deliberately reports only safe booleans, aggregate unresolved-event
counts, and stable reason codes.  It never exposes values from settings, tenant
identifiers, PII, encrypted payloads, provider configuration, or queue contents.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import providers
from app.core.config import get_settings
from app.models import Company, LineWebhookEvent, Store

settings = get_settings()

_UNRESOLVED_STATUSES = ("queued", "processing", "failed")
_BLOCKED_ERP_PROVIDERS = {"", "blocked"}
# One week is the longest operationally useful manual-review visibility window.
# Wider values would hide a stuck claim for too long, while zero and negatives are unsafe.
_MAX_PROCESSING_STALE_AFTER_SECONDS = 7 * 24 * 60 * 60


def _fernet_key_check() -> tuple[bool, str | None]:
    """Validate a Fernet key locally without encrypting, decrypting, or logging it."""
    key = settings.p1_pii_encryption_key.strip()
    if not key:
        return False, "P1_PII_ENCRYPTION_KEY_MISSING"
    try:
        Fernet(key.encode("utf-8"))
    except (TypeError, ValueError, UnicodeEncodeError):
        return False, "P1_PII_ENCRYPTION_KEY_INVALID"
    return True, None


def _identity_hmac_key_check() -> tuple[bool, str | None]:
    """Confirm the configured HMAC key is locally usable without revealing it.

    A SHA-256 HMAC key must be non-blank UTF-8 material at least 32 bytes long.
    The check performs only local key material validation and never returns or
    persists the key.
    """
    key = settings.p1_identity_hmac_key.strip()
    if not key:
        return False, "P1_IDENTITY_HMAC_KEY_MISSING"
    try:
        key_bytes = key.encode("utf-8")
        if len(key_bytes) < hashlib.sha256().digest_size:
            return False, "P1_IDENTITY_HMAC_KEY_INVALID"
        hmac.new(key_bytes, b"p1-readiness", hashlib.sha256).digest()
    except (TypeError, ValueError, UnicodeEncodeError):
        return False, "P1_IDENTITY_HMAC_KEY_INVALID"
    return True, None


def _processing_stale_after_seconds() -> tuple[int | None, str | None]:
    """Read a bounded positive stale-processing threshold without exposing its value."""
    raw_value = settings.p1_processing_stale_after_seconds
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None, "P1_PROCESSING_STALE_AFTER_SECONDS_MISSING"

    value = raw_value.strip()
    if not value.isascii() or not value.isdecimal():
        return None, "P1_PROCESSING_STALE_AFTER_SECONDS_INVALID"

    seconds = int(value)
    if not 1 <= seconds <= _MAX_PROCESSING_STALE_AFTER_SECONDS:
        return None, "P1_PROCESSING_STALE_AFTER_SECONDS_INVALID"
    return seconds, None


def _queue_provider_check() -> tuple[bool, str | None]:
    """Acquire the configured queue adapter without probing, reading, or enqueueing.

    The Redis adapter constructor only creates local client objects; it performs
    no ping or other network operation.  This function intentionally never calls
    ``depth`` or ``enqueue``.
    """
    try:
        providers.get_queue_for_readiness()
    except Exception:  # noqa: BLE001 - a missing optional adapter must fail closed.
        return False, "P1_QUEUE_PROVIDER_UNAVAILABLE"
    return True, None


def _erp_delivery_blocked() -> tuple[bool, str | None]:
    """Require the P1 ERP path to remain both provider-blocked and switch-disabled."""
    provider_blocked = settings.p1_erp_ingest_provider.strip().lower() in _BLOCKED_ERP_PROVIDERS
    delivery_disabled = not settings.p1_isolated_delivery_enabled and not settings.p1_uat_delivery_enabled
    if provider_blocked and delivery_disabled:
        return True, None
    return False, "P1_ERP_DELIVERY_NOT_BLOCKED"


def _resolve_company_scope(db: Session, store_id: int) -> int | None:
    """Resolve only the authorized store's company scope; never return it to callers."""
    return db.execute(
        select(Store.company_id)
        .join(Company, Company.id == Store.company_id)
        .where(
            Store.id == store_id,
            Store.company_id == Company.id,
        )
    ).scalar_one_or_none()


def _unresolved_event_counts(db: Session, *, store_id: int, company_id: int) -> dict[str, int]:
    """Return aggregate unresolved counts under both store and company constraints."""
    rows = db.execute(
        select(LineWebhookEvent.status, func.count(LineWebhookEvent.id))
        .join(
            Store,
            (Store.id == LineWebhookEvent.store_id)
            & (Store.company_id == LineWebhookEvent.company_id),
        )
        .where(
            LineWebhookEvent.store_id == store_id,
            LineWebhookEvent.company_id == company_id,
            Store.id == store_id,
            Store.company_id == company_id,
            LineWebhookEvent.status.in_(_UNRESOLVED_STATUSES),
        )
        .group_by(LineWebhookEvent.status)
    ).all()
    counts = {status: 0 for status in _UNRESOLVED_STATUSES}
    counts.update({status: int(count) for status, count in rows})
    return counts


def _stale_processing_count(
    db: Session, *, store_id: int, company_id: int, stale_after_seconds: int
) -> int:
    """Count stale processing claims within the authorized company and store only.

    This is a UTC, aggregate-only SELECT. It intentionally neither changes event
    state nor asks the queue to retry/rearm a claim.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
    return int(
        db.execute(
            select(func.count(LineWebhookEvent.id))
            .join(
                Store,
                (Store.id == LineWebhookEvent.store_id)
                & (Store.company_id == LineWebhookEvent.company_id),
            )
            .where(
                LineWebhookEvent.store_id == store_id,
                LineWebhookEvent.company_id == company_id,
                Store.id == store_id,
                Store.company_id == company_id,
                LineWebhookEvent.status == "processing",
                LineWebhookEvent.claimed_at.is_not(None),
                LineWebhookEvent.claimed_at < cutoff,
            )
        ).scalar_one()
    )


def _stale_queued_count(
    db: Session, *, store_id: int, company_id: int, stale_after_seconds: int
) -> int:
    """Count durable-but-never-claimed events without changing or retrying them."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
    return int(
        db.execute(
            select(func.count(LineWebhookEvent.id))
            .join(
                Store,
                (Store.id == LineWebhookEvent.store_id)
                & (Store.company_id == LineWebhookEvent.company_id),
            )
            .where(
                LineWebhookEvent.store_id == store_id,
                LineWebhookEvent.company_id == company_id,
                Store.id == store_id,
                Store.company_id == company_id,
                LineWebhookEvent.status == "queued",
                LineWebhookEvent.created_at < cutoff,
            )
        ).scalar_one()
    )


def get_p1_readiness(db: Session, *, store_id: int) -> dict[str, Any]:
    """Evaluate P1 readiness without changing database, queue, or delivery state.

    A production environment has no exception path for missing configuration:
    incomplete prerequisites remain ``ready=False`` and this service never enables
    P1 or delivery settings.
    """
    reason_codes: list[str] = []

    intake_enabled = bool(settings.p1_intake_enabled)
    if not intake_enabled:
        reason_codes.append("P1_INTAKE_DISABLED")

    company_id = _resolve_company_scope(db, store_id)
    scope_resolved = company_id is not None
    if not scope_resolved:
        reason_codes.append("P1_STORE_COMPANY_SCOPE_UNRESOLVED")

    encryption_key_valid, encryption_reason = _fernet_key_check()
    if encryption_reason:
        reason_codes.append(encryption_reason)

    identity_hmac_key_valid, hmac_reason = _identity_hmac_key_check()
    if hmac_reason:
        reason_codes.append(hmac_reason)

    stale_after_seconds, stale_threshold_reason = _processing_stale_after_seconds()
    if stale_threshold_reason:
        reason_codes.append(stale_threshold_reason)

    queue_provider_available, queue_reason = _queue_provider_check()
    if queue_reason:
        reason_codes.append(queue_reason)

    erp_delivery_blocked, erp_reason = _erp_delivery_blocked()
    if erp_reason:
        reason_codes.append(erp_reason)

    unresolved_event_counts = {status: 0 for status in _UNRESOLVED_STATUSES}
    stale_processing_count = 0
    stale_queued_count = 0
    if company_id is not None:
        unresolved_event_counts = _unresolved_event_counts(
            db, store_id=store_id, company_id=company_id
        )
        if stale_after_seconds is not None:
            stale_processing_count = _stale_processing_count(
                db,
                store_id=store_id,
                company_id=company_id,
                stale_after_seconds=stale_after_seconds,
            )
            stale_queued_count = _stale_queued_count(
                db,
                store_id=store_id,
                company_id=company_id,
                stale_after_seconds=stale_after_seconds,
            )
    has_stale_processing = stale_processing_count > 0
    has_stale_queued = stale_queued_count > 0
    if has_stale_processing:
        reason_codes.append("P1_STALE_PROCESSING_EVENTS")
    if has_stale_queued:
        reason_codes.append("P1_STALE_QUEUED_EVENTS")

    checks_ready = all(
        (
            intake_enabled,
            scope_resolved,
            encryption_key_valid,
            identity_hmac_key_valid,
            stale_after_seconds is not None,
            queue_provider_available,
            erp_delivery_blocked,
            not has_stale_processing,
            not has_stale_queued,
        )
    )
    production_incomplete = settings.environment.strip().lower() == "production" and not checks_ready
    if production_incomplete:
        reason_codes.append("P1_PRODUCTION_CONFIGURATION_INCOMPLETE")

    return {
        "ready": checks_ready and not production_incomplete,
        "checks": {
            "intake_enabled": intake_enabled,
            "store_company_scope_resolved": scope_resolved,
            "encryption_key_valid": encryption_key_valid,
            "identity_hmac_key_valid": identity_hmac_key_valid,
            "queue_provider_available": queue_provider_available,
            "erp_delivery_blocked": erp_delivery_blocked,
        },
        "unresolved_event_counts": unresolved_event_counts,
        "stale_processing_count": stale_processing_count,
        "has_stale_processing": has_stale_processing,
        "stale_queued_count": stale_queued_count,
        "has_stale_queued": has_stale_queued,
        "reason_codes": sorted(set(reason_codes)),
    }
