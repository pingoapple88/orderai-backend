"""Provider-neutral, fail-closed conformance checks for pending ERP intents.

The harness is deliberately an additive helper.  It accepts provider factories from
fake or sandbox tests and submits the *same* ``PendingOrderIntent`` whose trace
manifest is verified before every run.  It does not create endpoints, credentials,
authentication, transports, or provider selection paths.

Public evidence is intentionally restricted to contract version, one manifest hash,
controlled status/reason codes, and numeric counts.  Raw intent values, provider
names, references, and payloads never appear in its output.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence

from app.core.interfaces.erp_ingest import (
    ErpIngestBlockedError,
    ErpIngestResult,
    IErpIngestProvider,
    PendingOrderIntent,
)
from app.core.interfaces.erp_traceability import (
    PendingOrderTraceManifest,
    build_pending_order_trace_manifest,
    verify_pending_order_trace_manifest,
)


ProviderFactory = Callable[[], IErpIngestProvider]
_PUBLIC_EVIDENCE_KEYS = frozenset({"contract_version", "hash", "status", "reason_code", "counts"})


@dataclass(frozen=True)
class PendingOrderConformancePlan:
    """Provider factories and controlled expected codes for one reusable contract.

    Every factory receives no customer data and is invoked only by the local test
    harness.  Factories can create independent fake/sandbox adapters for each
    controlled outcome.  ``pending_provider`` is invoked once and then replayed
    with the exact same intent to prove reference stability.
    """

    contract_version: str
    intent: PendingOrderIntent
    blocked_provider: ProviderFactory
    manual_review_provider: ProviderFactory
    pending_provider: ProviderFactory
    timeout_provider: ProviderFactory
    unknown_provider: ProviderFactory
    manual_review_reason_code: str
    timeout_reason_code: str = "ERP_TIMEOUT"
    unknown_reason_code: str = "ERP_UNKNOWN_RESPONSE"
    manifest: Optional[PendingOrderTraceManifest] = None


@dataclass(frozen=True)
class PendingOrderConformanceEvidence:
    """A single PII-safe conformance outcome suitable for JSON evidence."""

    contract_version: str
    hash: str
    status: str
    reason_code: Optional[str]
    counts: Mapping[str, int]

    def public_record(self) -> dict[str, object]:
        """Return the strict public evidence schema without provider or intent data."""

        return {
            "contract_version": self.contract_version,
            "hash": self.hash,
            "status": self.status,
            "reason_code": self.reason_code,
            "counts": dict(self.counts),
        }


def _provider(factory: ProviderFactory) -> IErpIngestProvider:
    provider = factory()
    if not isinstance(provider, IErpIngestProvider):
        raise TypeError("ERP_CONFORMANCE_PROVIDER_INVALID")
    return provider


def _transaction_side_effect_counts(provider: IErpIngestProvider) -> dict[str, int]:
    """Assert zero observable transaction side effects if an adapter exposes them."""

    if not hasattr(provider, "transaction_side_effects"):
        return {}
    effects = getattr(provider, "transaction_side_effects")
    if callable(effects):
        effects = effects()
    try:
        count = effects if isinstance(effects, int) else len(effects)
    except TypeError as exc:
        raise AssertionError("ERP_CONFORMANCE_TRANSACTION_SIDE_EFFECTS_INVALID") from exc
    if count != 0:
        raise AssertionError("ERP_CONFORMANCE_TRANSACTION_SIDE_EFFECTS_NONZERO")
    return {"transaction_side_effects": 0}


def _counts(provider: IErpIngestProvider, *, attempts: int, replays: int) -> dict[str, int]:
    counts = {"attempts": attempts, "replays": replays}
    counts.update(_transaction_side_effect_counts(provider))
    return counts


def _require_result(
    result: ErpIngestResult,
    *,
    expected_status: str,
    expected_reason_code: Optional[str],
) -> None:
    """Check controlled outcomes without including result data in error messages."""

    if result.status != expected_status:
        raise AssertionError("ERP_CONFORMANCE_STATUS_MISMATCH")
    if result.reason_code != expected_reason_code:
        raise AssertionError("ERP_CONFORMANCE_REASON_CODE_MISMATCH")
    if not isinstance(result.reference, str) or not result.reference:
        raise AssertionError("ERP_CONFORMANCE_REFERENCE_MISSING")


def _manifest_for(plan: PendingOrderConformancePlan) -> PendingOrderTraceManifest:
    manifest = plan.manifest or build_pending_order_trace_manifest(
        plan.intent,
        contract_version=plan.contract_version,
    )
    verify_pending_order_trace_manifest(
        plan.intent,
        contract_version=plan.contract_version,
        manifest=manifest,
    )
    return manifest


def _evidence(
    manifest: PendingOrderTraceManifest,
    *,
    status: str,
    reason_code: Optional[str],
    counts: Mapping[str, int],
) -> PendingOrderConformanceEvidence:
    return PendingOrderConformanceEvidence(
        contract_version=manifest.contract_version,
        hash=manifest.idempotency_audit_binding_sha256,
        status=status,
        reason_code=reason_code,
        counts=counts,
    )


async def run_pending_order_conformance_async(
    plan: PendingOrderConformancePlan,
) -> tuple[PendingOrderConformanceEvidence, ...]:
    """Run blocked/manual-review/pending/replay/timeout/unknown conformance checks.

    ``timeout`` and ``unknown`` are required to fail closed as ``manual_review``;
    they can never be treated as accepted or pending.  The original pending result
    and its replay must keep the same non-empty reference.  Any optional
    ``transaction_side_effects`` exposure must remain empty after each scenario.
    """

    manifest = _manifest_for(plan)
    evidence: list[PendingOrderConformanceEvidence] = []

    blocked_provider = _provider(plan.blocked_provider)
    try:
        await blocked_provider.submit_pending_confirmation_intent(plan.intent)
    except ErpIngestBlockedError as exc:
        if exc.reason_code != "ERP_CONNECTION_BLOCKED":
            raise AssertionError("ERP_CONFORMANCE_BLOCKED_REASON_CODE_MISMATCH") from exc
    else:
        raise AssertionError("ERP_CONFORMANCE_BLOCKED_PROVIDER_ACCEPTED")
    evidence.append(
        _evidence(
            manifest,
            status="blocked",
            reason_code="ERP_CONNECTION_BLOCKED",
            counts=_counts(blocked_provider, attempts=1, replays=0),
        )
    )

    manual_review_provider = _provider(plan.manual_review_provider)
    manual_review = await manual_review_provider.submit_pending_confirmation_intent(plan.intent)
    _require_result(
        manual_review,
        expected_status="manual_review",
        expected_reason_code=plan.manual_review_reason_code,
    )
    evidence.append(
        _evidence(
            manifest,
            status=manual_review.status,
            reason_code=manual_review.reason_code,
            counts=_counts(manual_review_provider, attempts=1, replays=0),
        )
    )

    pending_provider = _provider(plan.pending_provider)
    pending = await pending_provider.submit_pending_confirmation_intent(plan.intent)
    _require_result(pending, expected_status="pending", expected_reason_code=None)
    evidence.append(
        _evidence(
            manifest,
            status=pending.status,
            reason_code=pending.reason_code,
            counts=_counts(pending_provider, attempts=1, replays=0),
        )
    )

    replay = await pending_provider.submit_pending_confirmation_intent(plan.intent)
    _require_result(replay, expected_status="pending", expected_reason_code=None)
    if replay.reference != pending.reference:
        raise AssertionError("ERP_CONFORMANCE_REPLAY_REFERENCE_UNSTABLE")
    evidence.append(
        _evidence(
            manifest,
            status=replay.status,
            reason_code=replay.reason_code,
            counts=_counts(pending_provider, attempts=2, replays=1),
        )
    )

    for factory, expected_reason_code in (
        (plan.timeout_provider, plan.timeout_reason_code),
        (plan.unknown_provider, plan.unknown_reason_code),
    ):
        provider = _provider(factory)
        result = await provider.submit_pending_confirmation_intent(plan.intent)
        _require_result(
            result,
            expected_status="manual_review",
            expected_reason_code=expected_reason_code,
        )
        evidence.append(
            _evidence(
                manifest,
                status=result.status,
                reason_code=result.reason_code,
                counts=_counts(provider, attempts=1, replays=0),
            )
        )

    return tuple(evidence)


def run_pending_order_conformance(
    plan: PendingOrderConformancePlan,
) -> tuple[PendingOrderConformanceEvidence, ...]:
    """Synchronously run the provider-neutral harness for pytest or a local CLI."""

    return asyncio.run(run_pending_order_conformance_async(plan))


def public_conformance_evidence(
    evidence: Sequence[PendingOrderConformanceEvidence],
) -> list[dict[str, object]]:
    """Serialize only the allowed public evidence fields for CLI/file output."""

    records = [item.public_record() for item in evidence]
    if any(set(record) != _PUBLIC_EVIDENCE_KEYS for record in records):
        raise AssertionError("ERP_CONFORMANCE_EVIDENCE_SCHEMA_INVALID")
    return records


class ErpPendingOrderConformanceMixin:
    """Reusable pytest-style mixin for fake or sandbox ERP adapter contract tests.

    A test class implements ``build_pending_order_conformance_plan`` and calls
    ``assert_pending_order_conformance``.  The mixin has no pytest dependency, so
    sandbox suites can use it with unittest or invoke the underlying helper directly.
    """

    def build_pending_order_conformance_plan(self) -> PendingOrderConformancePlan:
        raise NotImplementedError

    def assert_pending_order_conformance(self) -> tuple[PendingOrderConformanceEvidence, ...]:
        return run_pending_order_conformance(self.build_pending_order_conformance_plan())


__all__ = [
    "ErpPendingOrderConformanceMixin",
    "PendingOrderConformanceEvidence",
    "PendingOrderConformancePlan",
    "ProviderFactory",
    "public_conformance_evidence",
    "run_pending_order_conformance",
    "run_pending_order_conformance_async",
]
