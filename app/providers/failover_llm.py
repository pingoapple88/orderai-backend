"""LLM 備援 Adapter；僅在主 Provider 呼叫失敗時才切換，低信心結果仍由風險守衛 fail-closed。"""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from app.core.interfaces.llm_provider import ExtractionResult, ILLMProvider, LLMProviderExecutionError


class FailoverLLMProvider(ILLMProvider):
    """依序嘗試主／備 Provider，所有 Provider 失敗時不產生推測結果。"""

    provider_name = "failover"

    def __init__(self, primary: ILLMProvider, fallback: ILLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    async def extract_order(
        self,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        industry_type: str = "ecom",
    ) -> ExtractionResult:
        try:
            return await self.primary.extract_order(
                image_url=image_url,
                text=text,
                industry_type=industry_type,
            )
        except Exception as primary_error:
            try:
                return await self.fallback.extract_order(
                    image_url=image_url,
                    text=text,
                    industry_type=industry_type,
                )
            except Exception as fallback_error:
                errors = (primary_error, fallback_error)
                reason_code = "provider_timeout" if any(
                    isinstance(error, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError))
                    or getattr(error, "reason_code", None) == "provider_timeout"
                    for error in errors
                ) else "provider_error"
                raise LLMProviderExecutionError(
                    reason_code,
                    "All configured LLM providers failed; order requires manual review",
                ) from fallback_error
