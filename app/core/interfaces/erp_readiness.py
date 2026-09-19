"""Provider-neutral, fail-closed ERP delivery readiness manifests.

This module is an additive pre-submission helper.  It accepts only **already
reviewed boolean assertions**; it deliberately has no settings import and never
accepts, reads, serializes, or connects to endpoint, authentication, secret, or
identifier values.  Provider owners perform their sensitive configuration
checks elsewhere, then pass the resulting safe booleans here for uniform
CloudDing, Jiezhou, and future-ERP evidence.

A readiness manifest is not a provider selection or transport gate.  It makes
its decision locally and deterministically, leaving legacy ERP dataclasses and
adapters unchanged.  Unknown and formal-Jiezhou declarations are permanently
fail-closed in this helper: neither can claim a configured transport or enabled
formal delivery.  Synthetic fakes may report completed conformance while still
being unable to enable formal delivery.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from app.core.interfaces.erp_ingest import ErpIngestBlockedError


ERP_READINESS_MANIFEST_VERSION: Final = "orderai-erp-readiness-manifest-v1"
_SAFE_EVIDENCE_KEYS: Final = frozenset(
    {
        "manifest_version",
        "contract_version_supported",
        "mapping_complete",
        "tenant_scope_bound",
        "sales_location_scope_bound",
        "transport_configured",
        "formal_delivery_enabled",
        "conformance_passed",
        "reason_codes",
        "network_calls",
    }
)


class ErpReadinessMode(str, Enum):
    """Policy category for a readiness declaration, never emitted as evidence.

    The categories describe only delivery policy; they are not provider IDs,
    endpoint names, configuration references, or credentials.  ``UNKNOWN`` is
    the default so that accidental future-provider use cannot enable delivery.
    """

    UNKNOWN = "unknown"
    CLOUD_DING = "cloud_ding"
    JIEZHOU_FORMAL = "jiezhou_formal"
    SYNTHETIC = "synthetic"
    FUTURE_FORMAL = "future_formal"


@dataclass(frozen=True)
class ErpReadinessDeclaration:
    """Reviewed, value-free input for a pre-submission readiness assessment.

    Each field is a boolean conclusion from a provider owner's controlled
    review.  No endpoint, authentication material, secret, tenant/company/site
    identifier, mapping value, or contract value belongs in this declaration.
    ``formal_delivery_authorized`` is intentionally an internal approval signal:
    it affects the computed boolean but is never emitted in shared evidence.
    """

    mode: ErpReadinessMode = ErpReadinessMode.UNKNOWN
    contract_version_supported: bool = False
    mapping_complete: bool = False
    tenant_scope_bound: bool = False
    sales_location_scope_bound: bool = False
    transport_configured: bool = False
    conformance_passed: bool = False
    formal_delivery_authorized: bool = False

    @classmethod
    def synthetic(
        cls,
        *,
        contract_version_supported: bool,
        mapping_complete: bool,
        tenant_scope_bound: bool,
        sales_location_scope_bound: bool,
        conformance_passed: bool,
    ) -> "ErpReadinessDeclaration":
        """Build a fake/sandbox declaration that can never enable delivery.

        A synthetic configuration may truthfully report contract, mapping,
        scope, and conformance conclusions.  Its lack of a real transport and
        formal authorization is imposed here instead of trusting caller input.
        """

        return cls(
            mode=ErpReadinessMode.SYNTHETIC,
            contract_version_supported=contract_version_supported,
            mapping_complete=mapping_complete,
            tenant_scope_bound=tenant_scope_bound,
            sales_location_scope_bound=sales_location_scope_bound,
            transport_configured=False,
            conformance_passed=conformance_passed,
            formal_delivery_authorized=False,
        )


@dataclass(frozen=True)
class ErpDeliveryReadinessManifest:
    """PII- and configuration-safe delivery readiness result.

    The seven required capability booleans are intentionally exposed directly.
    ``reason_codes`` is a deterministic tuple of controlled code strings only;
    it never contains a provider, endpoint, credential, or identifier value.
    """

    manifest_version: str
    contract_version_supported: bool
    mapping_complete: bool
    tenant_scope_bound: bool
    sales_location_scope_bound: bool
    transport_configured: bool
    formal_delivery_enabled: bool
    conformance_passed: bool
    reason_codes: tuple[str, ...]

    def public_evidence(self) -> dict[str, object]:
        """Return the strict, JSON-safe manifest representation.

        Building a manifest performs no network activity.  The explicit zero is
        included to make that property auditable in CLI or test evidence.
        """

        return {
            "manifest_version": self.manifest_version,
            "contract_version_supported": self.contract_version_supported,
            "mapping_complete": self.mapping_complete,
            "tenant_scope_bound": self.tenant_scope_bound,
            "sales_location_scope_bound": self.sales_location_scope_bound,
            "transport_configured": self.transport_configured,
            "formal_delivery_enabled": self.formal_delivery_enabled,
            "conformance_passed": self.conformance_passed,
            "reason_codes": list(self.reason_codes),
            "network_calls": 0,
        }

    def require_formal_delivery(self) -> None:
        """Raise a controlled fail-closed error if formal delivery is disabled."""

        if not self.formal_delivery_enabled:
            reason_code = self.reason_codes[0] if self.reason_codes else "ERP_CONNECTION_BLOCKED"
            raise ErpIngestBlockedError(reason_code)


def _normalized_mode(mode: ErpReadinessMode) -> ErpReadinessMode:
    """Reject non-enum inputs rather than guessing a future provider policy."""

    if not isinstance(mode, ErpReadinessMode):
        return ErpReadinessMode.UNKNOWN
    return mode


def _append_reason(reason_codes: list[str], condition: bool, reason_code: str) -> None:
    """Append a controlled reason once, preserving deterministic priority."""

    if condition and reason_code not in reason_codes:
        reason_codes.append(reason_code)


def build_erp_delivery_readiness_manifest(
    declaration: ErpReadinessDeclaration | None = None,
) -> ErpDeliveryReadinessManifest:
    """Build an offline pre-submission readiness manifest from safe booleans.

    The function does not instantiate a provider, read settings, inspect a
    provider's fields, or make an I/O call.  Therefore a CloudDing or future
    provider can be represented without leaking its connection configuration.
    Unknown and formal-Jiezhou modes override caller assertions for transport
    and formal delivery, preserving their mandatory ``ERP_CONNECTION_BLOCKED``
    fail-closed status.  Synthetic mode likewise cannot enable a transport or
    formal delivery, but may retain a passed conformance result.
    """

    declaration = declaration or ErpReadinessDeclaration()
    if not isinstance(declaration, ErpReadinessDeclaration):
        raise TypeError("ERP_READINESS_DECLARATION_INVALID")

    mode = _normalized_mode(declaration.mode)
    transport_configured = bool(declaration.transport_configured)
    formal_delivery_authorized = bool(declaration.formal_delivery_authorized)

    if mode in {
        ErpReadinessMode.UNKNOWN,
        ErpReadinessMode.JIEZHOU_FORMAL,
        ErpReadinessMode.SYNTHETIC,
    }:
        transport_configured = False
        formal_delivery_authorized = False

    contract_version_supported = bool(declaration.contract_version_supported)
    mapping_complete = bool(declaration.mapping_complete)
    tenant_scope_bound = bool(declaration.tenant_scope_bound)
    sales_location_scope_bound = bool(declaration.sales_location_scope_bound)
    conformance_passed = bool(declaration.conformance_passed)
    formal_delivery_enabled = all(
        (
            contract_version_supported,
            mapping_complete,
            tenant_scope_bound,
            sales_location_scope_bound,
            transport_configured,
            conformance_passed,
            formal_delivery_authorized,
        )
    )

    # Connection is deliberately first so callers that use require_formal_delivery
    # receive the mandated fail-closed code for unknown/formal-Jiezhou modes.
    reason_codes: list[str] = []
    _append_reason(reason_codes, not transport_configured, "ERP_CONNECTION_BLOCKED")
    _append_reason(reason_codes, not contract_version_supported, "ERP_CONTRACT_UNCONFIRMED")
    _append_reason(reason_codes, not mapping_complete, "ERP_PRODUCT_MAPPING_MISSING")
    _append_reason(reason_codes, not tenant_scope_bound, "ERP_TENANT_SCOPE_UNBOUND")
    _append_reason(reason_codes, not sales_location_scope_bound, "ERP_SALES_LOCATION_SCOPE_UNBOUND")
    _append_reason(reason_codes, not conformance_passed, "ERP_CONFORMANCE_NOT_PASSED")
    _append_reason(
        reason_codes,
        not formal_delivery_enabled and transport_configured and not formal_delivery_authorized,
        "ERP_FORMAL_DELIVERY_DISABLED",
    )

    return ErpDeliveryReadinessManifest(
        manifest_version=ERP_READINESS_MANIFEST_VERSION,
        contract_version_supported=contract_version_supported,
        mapping_complete=mapping_complete,
        tenant_scope_bound=tenant_scope_bound,
        sales_location_scope_bound=sales_location_scope_bound,
        transport_configured=transport_configured,
        formal_delivery_enabled=formal_delivery_enabled,
        conformance_passed=conformance_passed,
        reason_codes=tuple(reason_codes),
    )


def public_erp_delivery_readiness_evidence(
    manifest: ErpDeliveryReadinessManifest,
) -> dict[str, object]:
    """Serialize one manifest and enforce its strict, value-free public schema."""

    if not isinstance(manifest, ErpDeliveryReadinessManifest):
        raise TypeError("ERP_READINESS_MANIFEST_INVALID")
    evidence = manifest.public_evidence()
    if set(evidence) != _SAFE_EVIDENCE_KEYS:
        raise AssertionError("ERP_READINESS_EVIDENCE_SCHEMA_INVALID")
    return evidence


__all__ = [
    "ERP_READINESS_MANIFEST_VERSION",
    "ErpDeliveryReadinessManifest",
    "ErpReadinessDeclaration",
    "ErpReadinessMode",
    "build_erp_delivery_readiness_manifest",
    "public_erp_delivery_readiness_evidence",
]
