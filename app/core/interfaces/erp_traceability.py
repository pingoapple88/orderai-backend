"""Provider-neutral, PII-safe traceability manifests for pending ERP intents.

The manifest is intentionally an additive helper rather than a field on
``PendingOrderIntent``.  Existing providers therefore retain their current
constructor and transport contracts.  It produces stable SHA-256 evidence for
an already-defined provider-neutral intent and never serializes its raw values
into smoke evidence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from app.core.interfaces.erp_ingest import PendingOrderIntent


TRACE_MANIFEST_VERSION = "orderai-erp-trace-manifest-v1"
CANONICAL_INTENT_VERSION = "orderai-provider-neutral-pending-order-intent-v1"


@dataclass(frozen=True)
class PendingOrderTraceManifest:
    """Comparable, PII-safe evidence for one provider-neutral pending intent.

    ``contract_version`` is a controlled contract/document version supplied by
    the configured provider mapping; it is not a formal ERP field.  The other
    values are SHA-256 digests only.  ``idempotency_audit_binding_sha256`` binds
    both opaque references to this exact intent and contract version, so a
    partner can detect partial or cross-case evidence substitution without
    receiving either raw reference.
    """

    manifest_version: str
    canonical_intent_version: str
    contract_version: str
    intent_sha256: str
    idempotency_key_sha256: str
    audit_reference_sha256: str
    idempotency_audit_binding_sha256: str

    def comparison_evidence(self) -> dict[str, str]:
        """Return the only manifest representation intended for shared evidence."""

        return {
            "manifest_version": self.manifest_version,
            "canonical_intent_version": self.canonical_intent_version,
            "contract_version": self.contract_version,
            "intent_sha256": self.intent_sha256,
            "idempotency_key_sha256": self.idempotency_key_sha256,
            "audit_reference_sha256": self.audit_reference_sha256,
            "idempotency_audit_binding_sha256": self.idempotency_audit_binding_sha256,
        }


def _canonical_json(value: Any) -> bytes:
    """Serialize known neutral values deterministically for SHA-256 input."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _opaque_reference_sha256(value: str) -> str:
    """Hash an opaque reference as a JSON string to retain its exact identity."""

    return _sha256(value)


def canonical_pending_order_intent_payload(intent: PendingOrderIntent) -> dict[str, Any]:
    """Return the versioned canonical payload used only to calculate ``intent_sha256``.

    Mapping order and item display order are intentionally normalized.  Item
    multiplicity is retained, and no payment, inventory, shipment, invoice, or
    provider-specific fields are introduced.
    """

    canonical_items = [
        {
            "source_product_key": item.source_product_key,
            "product_name": item.product_name,
            "quantity": item.quantity,
            "unit": item.unit,
        }
        for item in intent.content.items
    ]
    canonical_items.sort(key=lambda item: _canonical_json(item))
    return {
        "canonical_intent_version": CANONICAL_INTENT_VERSION,
        "tenant_id": intent.tenant_id,
        "company_id": intent.company_id,
        "sales_location_id": intent.sales_location_id,
        "source_event_id": intent.source_event_id,
        "content": {
            "buyer_name": intent.content.buyer_name,
            "buyer_contact_reference": intent.content.buyer_contact_reference,
            "requested_for": intent.content.requested_for,
            "special_request": intent.content.special_request,
            "items": canonical_items,
        },
        "product_mapping": dict(intent.product_mapping),
    }


def _require_trace_inputs(intent: PendingOrderIntent, contract_version: str) -> str:
    normalized_contract_version = contract_version.strip()
    if not normalized_contract_version:
        raise ValueError("ERP_TRACE_CONTRACT_VERSION_MISSING")
    if not intent.idempotency_key.strip():
        raise ValueError("ERP_IDEMPOTENCY_KEY_MISSING")
    if not intent.audit_reference.strip():
        raise ValueError("ERP_AUDIT_REFERENCE_MISSING")
    return normalized_contract_version


def build_pending_order_trace_manifest(
    intent: PendingOrderIntent,
    *,
    contract_version: str,
) -> PendingOrderTraceManifest:
    """Build a deterministic manifest without modifying the provider contract."""

    normalized_contract_version = _require_trace_inputs(intent, contract_version)
    intent_sha256 = _sha256(canonical_pending_order_intent_payload(intent))
    idempotency_key_sha256 = _opaque_reference_sha256(intent.idempotency_key)
    audit_reference_sha256 = _opaque_reference_sha256(intent.audit_reference)
    idempotency_audit_binding_sha256 = _sha256(
        {
            "manifest_version": TRACE_MANIFEST_VERSION,
            "canonical_intent_version": CANONICAL_INTENT_VERSION,
            "contract_version": normalized_contract_version,
            "intent_sha256": intent_sha256,
            "idempotency_key_sha256": idempotency_key_sha256,
            "audit_reference_sha256": audit_reference_sha256,
        }
    )
    return PendingOrderTraceManifest(
        manifest_version=TRACE_MANIFEST_VERSION,
        canonical_intent_version=CANONICAL_INTENT_VERSION,
        contract_version=normalized_contract_version,
        intent_sha256=intent_sha256,
        idempotency_key_sha256=idempotency_key_sha256,
        audit_reference_sha256=audit_reference_sha256,
        idempotency_audit_binding_sha256=idempotency_audit_binding_sha256,
    )


def pending_order_trace_validation_reason(
    intent: PendingOrderIntent,
    *,
    contract_version: str,
    manifest: PendingOrderTraceManifest,
) -> Optional[str]:
    """Return a controlled mismatch code for an externally compared manifest.

    This confirms the canonical intent digest, contract version, each opaque
    reference digest, and their shared binding.  Returned codes contain no
    intent, customer, or opaque-reference values.
    """

    try:
        expected = build_pending_order_trace_manifest(intent, contract_version=contract_version)
    except ValueError as exc:
        return str(exc)

    if manifest.manifest_version != TRACE_MANIFEST_VERSION:
        return "ERP_TRACE_MANIFEST_VERSION_MISMATCH"
    if manifest.canonical_intent_version != CANONICAL_INTENT_VERSION:
        return "ERP_TRACE_CANONICAL_INTENT_VERSION_MISMATCH"
    if manifest.contract_version != expected.contract_version:
        return "ERP_TRACE_CONTRACT_VERSION_MISMATCH"
    if manifest.intent_sha256 != expected.intent_sha256:
        return "ERP_TRACE_INTENT_SHA256_MISMATCH"
    if manifest.idempotency_key_sha256 != expected.idempotency_key_sha256:
        return "ERP_TRACE_IDEMPOTENCY_REFERENCE_MISMATCH"
    if manifest.audit_reference_sha256 != expected.audit_reference_sha256:
        return "ERP_TRACE_AUDIT_REFERENCE_MISMATCH"
    if manifest.idempotency_audit_binding_sha256 != expected.idempotency_audit_binding_sha256:
        return "ERP_TRACE_IDEMPOTENCY_AUDIT_BINDING_MISMATCH"
    return None


def verify_pending_order_trace_manifest(
    intent: PendingOrderIntent,
    *,
    contract_version: str,
    manifest: PendingOrderTraceManifest,
) -> None:
    """Raise a controlled non-PII error when a manifest cannot be verified."""

    reason = pending_order_trace_validation_reason(
        intent,
        contract_version=contract_version,
        manifest=manifest,
    )
    if reason:
        raise ValueError(reason)


__all__ = [
    "CANONICAL_INTENT_VERSION",
    "TRACE_MANIFEST_VERSION",
    "PendingOrderTraceManifest",
    "build_pending_order_trace_manifest",
    "canonical_pending_order_intent_payload",
    "pending_order_trace_validation_reason",
    "verify_pending_order_trace_manifest",
]
