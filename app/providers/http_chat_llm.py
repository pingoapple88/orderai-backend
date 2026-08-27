"""通用 HTTP LLM Adapter；模型與端點由 ENV 注入，業務層只依賴 ILLMProvider。"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

import httpx

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult, ILLMProvider
from app.services.parse_normalizer import clean_product_name, normalize_quantity
from app.services.pii_redaction import redact_pii


_ORDER_PROMPTS = {
    "ecom": """你是繁體中文訂單資料抽取器。僅抽取使用者原文中明確出現的客戶、商品與數量。
禁止補猜商品、數量、價格、單位、姓名或電話。使用者沒有明講的欄位必須回傳 null 或空陣列。
每個商品必須保留 evidence（原文對應片段）並提供 0 到 1 的 field_confidence。
只回傳 JSON：
{"customer_name": string|null, "customer_phone": string|null,
 "items": [{"product_name": string, "quantity": integer|null, "unit": string|null,
             "evidence": string, "field_confidence": number}],
 "confidence_score": number, "field_confidence": {"customer_name": number, "items": number}}
""",
    "food": """你是繁體中文餐飲訂單資料抽取器。僅抽取使用者原文中明確出現的客戶、餐點與數量。
禁止補猜餐點、數量、價格、加料或取餐資訊。沒有明講的欄位必須回傳 null 或空陣列。
每個商品必須保留 evidence（原文對應片段）並提供 0 到 1 的 field_confidence。
只回傳 JSON：
{"customer_name": string|null, "customer_phone": string|null,
 "items": [{"product_name": string, "quantity": integer|null, "unit": string|null,
             "evidence": string, "field_confidence": number}],
 "confidence_score": number, "field_confidence": {"customer_name": number, "items": number}}
""",
    "beauty": """你是繁體中文預約資料抽取器。僅抽取使用者原文明確出現的服務、時間與人員。
禁止補猜服務、價格、人員或時段。沒有明講的欄位必須回傳 null 或空陣列。
只回傳 JSON：
{"customer_name": string|null, "customer_phone": string|null,
 "items": [{"product_name": string, "quantity": integer|null, "appointment_time": string|null,
             "staff_name": string|null, "evidence": string, "field_confidence": number}],
 "confidence_score": number, "field_confidence": {"customer_name": number, "items": number}}
""",
}


def _clamp_confidence(value: Any) -> float:
    try:
        numeric = float(value)
        if not math.isfinite(numeric):
            return 0.0
        return max(0.0, min(1.0, numeric))
    except (TypeError, ValueError):
        return 0.0


def _optional_text(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _parse_result(payload: Dict[str, Any], industry_type: str, provider_name: str) -> ExtractionResult:
    if not isinstance(payload, dict):
        payload = {"items": [], "confidence_score": 0}
    items: List[ExtractedItem] = []
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raw_items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        quantity = normalize_quantity(item.get("quantity")).value
        items.append(
            ExtractedItem(
                product_name=clean_product_name(item.get("product_name")),
                quantity=quantity,
                unit=_optional_text(item.get("unit")),
                appointment_time=_optional_text(item.get("appointment_time")),
                staff_name=_optional_text(item.get("staff_name")),
                evidence=clean_product_name(item.get("evidence")),
                confidence_score=_clamp_confidence(item.get("field_confidence")),
            )
        )
    raw_field_confidence = payload.get("field_confidence")
    if not isinstance(raw_field_confidence, dict):
        raw_field_confidence = {}
    field_confidence = {
        str(key): _clamp_confidence(value)
        for key, value in raw_field_confidence.items()
    }
    return ExtractionResult(
        items=items,
        customer_name=_optional_text(payload.get("customer_name")),
        customer_phone=_optional_text(payload.get("customer_phone")),
        confidence_score=_clamp_confidence(payload.get("confidence_score")),
        field_confidence=field_confidence,
        industry_type=industry_type,
        provider_name=provider_name,
        raw={"item_count": len(items)},
    )


async def _post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict | None = None,
    payload: dict,
    max_retries: int,
) -> httpx.Response:
    """只重試傳輸層 HTTP 錯誤；最終失敗交由 Worker 以原因碼 fail-closed。"""
    retries = max(0, max_retries)
    for attempt in range(retries + 1):
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response
        except httpx.HTTPError:
            if attempt >= retries:
                raise
    raise RuntimeError("unreachable")


class OpenAICompatibleLLMProvider(ILLMProvider):
    """支援 chat-completions 類型 HTTP 協定的 Adapter。"""

    provider_name = "openai_compatible"

    def __init__(
        self,
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        timeout_seconds: int = 60,
        temperature: float = 0.0,
        max_retries: int = 0,
        allow_empty_api_key: bool = False,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_retries = max_retries
        self.allow_empty_api_key = allow_empty_api_key

    async def extract_order(
        self,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        industry_type: str = "ecom",
    ) -> ExtractionResult:
        if not self.api_key and not self.allow_empty_api_key:
            raise RuntimeError("LLM_API_KEY not configured")
        if not self.api_base or not self.model:
            raise RuntimeError("LLM_API_BASE and LLM_MODEL must be configured")
        content: List[dict] = [{"type": "text", "text": redact_pii(text)}]
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer {}".format(self.api_key)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await _post_json(
                client,
                "{}/chat/completions".format(self.api_base.rstrip("/")),
                headers=headers,
                payload={
                    "model": self.model,
                    "temperature": self.temperature,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _ORDER_PROMPTS.get(industry_type, _ORDER_PROMPTS["ecom"])},
                        {"role": "user", "content": content},
                    ],
                },
                max_retries=self.max_retries,
            )
        raw_content = response.json()["choices"][0]["message"]["content"]
        try:
            payload = json.loads(raw_content)
        except (TypeError, json.JSONDecodeError):
            payload = {"items": [], "confidence_score": 0}
        return _parse_result(payload, industry_type, self.provider_name)


class OllamaLLMProvider(ILLMProvider):
    """Ollama `/api/chat` 的 HTTP Adapter；不依賴供應商 Python SDK。"""

    provider_name = "ollama"

    def __init__(
        self,
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        timeout_seconds: int = 60,
        temperature: float = 0.0,
        max_retries: int = 0,
        allow_empty_api_key: bool = False,
    ) -> None:
        self.api_base = api_base
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_retries = max_retries

    async def extract_order(
        self,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        industry_type: str = "ecom",
    ) -> ExtractionResult:
        if not self.api_base or not self.model:
            raise RuntimeError("LLM_API_BASE and LLM_MODEL must be configured")
        if image_url:
            raise RuntimeError("Ollama image URL input is not supported by this adapter")
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await _post_json(
                client,
                "{}/api/chat".format(self.api_base.rstrip("/")),
                payload={
                    "model": self.model,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": self.temperature},
                    "messages": [
                        {"role": "system", "content": _ORDER_PROMPTS.get(industry_type, _ORDER_PROMPTS["ecom"])},
                        {"role": "user", "content": redact_pii(text)},
                    ],
                },
                max_retries=self.max_retries,
            )
        raw_content = response.json()["message"]["content"]
        try:
            payload = json.loads(raw_content)
        except (TypeError, json.JSONDecodeError):
            payload = {"items": [], "confidence_score": 0}
        return _parse_result(payload, industry_type, self.provider_name)


class AnthropicMessagesLLMProvider(ILLMProvider):
    """Messages HTTP Adapter；不使用供應商 SDK。"""

    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        timeout_seconds: int = 60,
        temperature: float = 0.0,
        max_retries: int = 0,
        allow_empty_api_key: bool = False,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_retries = max_retries
        self.allow_empty_api_key = allow_empty_api_key

    async def extract_order(
        self,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        industry_type: str = "ecom",
    ) -> ExtractionResult:
        if not self.api_key and not self.allow_empty_api_key:
            raise RuntimeError("LLM_API_KEY not configured")
        if not self.api_base or not self.model:
            raise RuntimeError("LLM_API_BASE and LLM_MODEL must be configured")
        content: List[dict] = [{"type": "text", "text": redact_pii(text)}]
        if image_url:
            content.append({"type": "image", "source": {"type": "url", "url": image_url}})
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await _post_json(
                client,
                "{}/messages".format(self.api_base.rstrip("/")),
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                payload={
                    "model": self.model,
                    "max_tokens": 1024,
                    "temperature": self.temperature,
                    "system": _ORDER_PROMPTS.get(industry_type, _ORDER_PROMPTS["ecom"]),
                    "messages": [{"role": "user", "content": content}],
                },
                max_retries=self.max_retries,
            )
        raw_content = response.json()["content"][0]["text"]
        try:
            payload = json.loads(raw_content)
        except (TypeError, json.JSONDecodeError):
            payload = {"items": [], "confidence_score": 0}
        return _parse_result(payload, industry_type, self.provider_name)
