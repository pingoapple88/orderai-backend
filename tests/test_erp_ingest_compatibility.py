"""Compatibility tests for non-breaking ERP ingest contract extensions."""
import asyncio

import pytest

from app.core.interfaces.erp_ingest import (
    ErpIngestBlockedError,
    ErpIngestRequest,
    ErpIngestResult,
    IErpIngestProvider,
    PendingConfirmationOrderRequest,
    PendingCustomerRequest,
)


class _LegacyThirdPartyProvider(IErpIngestProvider):
    """Implements the IErpIngestProvider contract that existed before Jiezhou."""

    async def submit_pending_order(self, request: ErpIngestRequest) -> ErpIngestResult:
        raise NotImplementedError

    async def create_pending_customer(self, request: PendingCustomerRequest) -> ErpIngestResult:
        raise NotImplementedError

    async def submit_pending_confirmation_order(
        self, request: PendingConfirmationOrderRequest
    ) -> ErpIngestResult:
        raise NotImplementedError


def test_legacy_third_party_provider_remains_constructible_and_fails_closed_for_new_intent():
    provider = _LegacyThirdPartyProvider()

    with pytest.raises(ErpIngestBlockedError) as exc:
        asyncio.run(provider.submit_pending_confirmation_intent(None))

    assert exc.value.reason_code == "ERP_CONTRACT_MISMATCH"
