"""Jiezhou pending-order providers for Issue #39.

The production-facing provider is deliberately blocked.  It has no endpoint, auth,
or HTTP client because Jiezhou has not supplied a written contract or sandbox.  The
fake provider is deterministic and in-memory for synthetic contract tests only; it
creates neither payment, inventory, shipment, invoice, nor formal-order side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Mapping

from app.core.interfaces.erp_ingest import (
    ErpIngestBlockedError,
    ErpIngestRequest,
    ErpIngestResult,
    IErpIngestProvider,
    PendingConfirmationOrderRequest,
    PendingCustomerRequest,
    PendingOrderIntent,
    PendingOrderMappingConfig,
)


class JiezhouBlockedErpIngestProvider(IErpIngestProvider):
    """Formal Jiezhou provider: always fail closed until owner-approved implementation.

    No endpoint, credentials, request serialization, or transport is intentionally
    present in this class.  A future implementation requires an explicit provider
    selection plus every non-secret scope/mapping setting and a human-confirmed
    contract before it can replace this blocked adapter.
    """

    name = "jiezhou_blocked"

    def __init__(self, reason_code: str = "ERP_CONNECTION_BLOCKED") -> None:
        self.reason_code = reason_code

    def _blocked(self) -> None:
        raise ErpIngestBlockedError(
            self.reason_code,
            "捷州 ERP endpoint、認證、欄位及錯誤契約均為 [TODO: 待人工確認]；本 adapter 不送資料。",
        )

    async def submit_pending_order(self, request: ErpIngestRequest) -> ErpIngestResult:
        self._blocked()

    async def create_pending_customer(self, request: PendingCustomerRequest) -> ErpIngestResult:
        self._blocked()

    async def submit_pending_confirmation_order(
        self, request: PendingConfirmationOrderRequest
    ) -> ErpIngestResult:
        self._blocked()

    async def submit_pending_confirmation_intent(
        self, request: PendingOrderIntent
    ) -> ErpIngestResult:
        self._blocked()


@dataclass
class FakeJiezhouErpIngestProvider(IErpIngestProvider):
    """Deterministic in-memory synthetic contract provider.

    It only accepts ``PendingOrderIntent`` and returns ``pending`` rather than any
    formal transaction success.  Config, scope, and mapping failures return a
    controlled ``manual_review`` result.  ``timeout`` and ``unknown`` outcomes are
    synthetic test cases, also sent to manual review.  It never performs I/O.
    """

    mapping_config: PendingOrderMappingConfig
    outcome_by_source_event: Mapping[str, str] = field(default_factory=dict)
    accepted_by_idempotency_key: dict[str, ErpIngestResult] = field(default_factory=dict, init=False)
    recorded_intents: list[PendingOrderIntent] = field(default_factory=list, init=False)

    name = "jiezhou_fake"

    @property
    def transaction_side_effects(self) -> tuple[()]:
        """Explicit evidence: fake does not produce payment/inventory/etc. records."""

        return ()

    @staticmethod
    def _reference(prefix: str, idempotency_key: str) -> str:
        digest = sha256(idempotency_key.encode("utf-8")).hexdigest()[:20]
        return f"{prefix}-{digest}"

    async def submit_pending_confirmation_intent(
        self, request: PendingOrderIntent
    ) -> ErpIngestResult:
        validation_reason = self.mapping_config.validation_reason(request)
        if validation_reason:
            return ErpIngestResult(
                provider=self.name,
                reference=self._reference("jz-manual", request.idempotency_key),
                status="manual_review",
                reason_code=validation_reason,
            )

        previous = self.accepted_by_idempotency_key.get(request.idempotency_key)
        if previous is not None:
            return previous

        outcome = self.outcome_by_source_event.get(request.source_event_id, "pending")
        if outcome == "timeout":
            result = ErpIngestResult(
                provider=self.name,
                reference=self._reference("jz-manual", request.idempotency_key),
                status="manual_review",
                reason_code="ERP_TIMEOUT",
            )
        elif outcome == "unknown":
            result = ErpIngestResult(
                provider=self.name,
                reference=self._reference("jz-manual", request.idempotency_key),
                status="manual_review",
                reason_code="ERP_UNKNOWN_RESPONSE",
            )
        else:
            result = ErpIngestResult(
                provider=self.name,
                reference=self._reference("jz-pending", request.idempotency_key),
                status="pending",
            )

        self.accepted_by_idempotency_key[request.idempotency_key] = result
        self.recorded_intents.append(request)
        return result

    async def submit_pending_order(self, request: ErpIngestRequest) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONTRACT_MISMATCH",
            "捷州 fake 僅接受 provider-neutral 待確認訂單意圖。",
        )

    async def create_pending_customer(self, request: PendingCustomerRequest) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONTRACT_MISMATCH",
            "捷州 synthetic contract 未定義待確認客戶欄位；[TODO: 待人工確認]。",
        )

    async def submit_pending_confirmation_order(
        self, request: PendingConfirmationOrderRequest
    ) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONTRACT_MISMATCH",
            "捷州 fake 必須使用 PendingOrderIntent，禁止套用其他 ERP 的欄位。",
        )
