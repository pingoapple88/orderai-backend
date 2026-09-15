from __future__ import annotations

import pytest
import httpx

from app.core.interfaces.llm_provider import ExtractionResult, ILLMProvider, LLMProviderExecutionError
from app.providers.failover_llm import FailoverLLMProvider


class StubProvider(ILLMProvider):
    def __init__(self, result: ExtractionResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def extract_order(self, image_url=None, text=None, industry_type="ecom") -> ExtractionResult:
        self.calls += 1
        if self.error:
            raise self.error
        return self.result or ExtractionResult()


@pytest.mark.asyncio
async def test_primary_success_does_not_call_fallback():
    primary = StubProvider(result=ExtractionResult(provider_name="openai"))
    fallback = StubProvider(result=ExtractionResult(provider_name="claude"))

    result = await FailoverLLMProvider(primary, fallback).extract_order(text="蘋果 2 顆")

    assert result.provider_name == "openai"
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_primary_failure_uses_fallback_provider():
    primary = StubProvider(error=RuntimeError("primary unavailable"))
    fallback = StubProvider(result=ExtractionResult(provider_name="claude"))

    result = await FailoverLLMProvider(primary, fallback).extract_order(text="蘋果 2 顆")

    assert result.provider_name == "claude"
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_all_provider_failures_remain_fail_closed():
    provider = FailoverLLMProvider(
        StubProvider(error=RuntimeError("primary unavailable")),
        StubProvider(error=RuntimeError("fallback unavailable")),
    )

    with pytest.raises(LLMProviderExecutionError, match="manual review") as exc:
        await provider.extract_order(text="蘋果 2 顆")
    assert exc.value.reason_code == "provider_error"


@pytest.mark.asyncio
async def test_all_provider_timeouts_remain_fail_closed_with_timeout_reason():
    provider = FailoverLLMProvider(
        StubProvider(error=httpx.TimeoutException("primary timeout")),
        StubProvider(error=httpx.TimeoutException("fallback timeout")),
    )

    with pytest.raises(LLMProviderExecutionError, match="manual review") as exc:
        await provider.extract_order(text="蘋果 2 顆")
    assert exc.value.reason_code == "provider_timeout"
