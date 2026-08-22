"""以 HTTP 實作可替換的聊天模型 Adapter。

業務層只依賴 ILLMProvider；各家協定差異封裝在此檔，模型、端點與 Key 一律由 ENV 注入。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult, ILLMProvider


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
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _parse_result(payload: Dict[str, Any], industry_type: str, provider_name: str) -> ExtractionResult:
    if not isinstance(payload, dict):
        payload = {"items": [], "confidence_score": 0}
    items: List[ExtractedItem] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        quantity = item.get("quantity")
        try:
            quantity = int(quantity) if quantity is not None else None
        except (TypeError, ValueError):
            quantity = None
        items.append(
            ExtractedItem(
                product_name=str(item.get("product_name") or "").strip(),
                quantity=quantity,
                unit=item.get("unit"),
                appointment_time=item.get("appointment_time"),
                staff_name=item.get("staff_name"),
                evidence=str(item.get("evidence") or "").strip(),
                confidence_score=_clamp_confidence(item.get("field_confidence")),
            )
        )
    field_confidence = {
        str(key): _clamp_confidence(value)
        for key, value in (payload.get("field_confidence") or {}).items()
    }
    return ExtractionResult(
        items=items,
        customer_name=payload.get("customer_name"),
        customer_phone=payload.get("customer_phone"),
        confidence_score=_clamp_confidence(payload.get("confidence_score")),
        field_confidence=field_confidence,
        industry_type=industry_type,
        provider_name=provider_name,
        raw=payload,
    )


class OpenAICompatibleLLMProvider(ILLMProvider):
    """支援 OpenAI-compatible chat-completions 的 HTTP Adapter。"""

    provider_name = "openai_compatible"

    async def extract_order(
        self,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        industry_type: str = "ecom",
    ) -> ExtractionResult:
        settings = get_settings()
        if not settings.llm_api_key and not settings.llm_allow_empty_api_key:
            raise RuntimeError("LLM_API_KEY not configured")
        if not settings.llm_api_base or not settings.llm_model:
            raise RuntimeError("LLM_API_BASE and LLM_MODEL must be configured")

        content: List[dict] = [{"type": "text", "text": text or ""}]
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})
        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = "Bearer {}".format(settings.llm_api_key)

        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                "{}/chat/completions".format(settings.llm_api_base.rstrip("/")),
                headers=headers,
                json={
                    "model": settings.llm_model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _ORDER_PROMPTS.get(industry_type, _ORDER_PROMPTS["ecom"])},
                        {"role": "user", "content": content},
                    ],
                },
            )
            response.raise_for_status()
        raw_content = response.json()["choices"][0]["message"]["content"]
        try:
            payload = json.loads(raw_content)
        except (TypeError, json.JSONDecodeError):
            payload = {"items": [], "confidence_score": 0}
        return _parse_result(payload, industry_type, self.provider_name)


class OllamaLLMProvider(ILLMProvider):
    """Ollama `/api/chat` 的 HTTP Adapter；不依賴 Ollama Python SDK。"""

    provider_name = "ollama"

    async def extract_order(
        self,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        industry_type: str = "ecom",
    ) -> ExtractionResult:
        settings = get_settings()
        if not settings.llm_api_base or not settings.llm_model:
            raise RuntimeError("LLM_API_BASE and LLM_MODEL must be configured")
        if image_url:
            raise RuntimeError("Ollama image URL input is not supported by this adapter")
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                "{}/api/chat".format(settings.llm_api_base.rstrip("/")),
                json={
                    "model": settings.llm_model,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0},
                    "messages": [
                        {"role": "system", "content": _ORDER_PROMPTS.get(industry_type, _ORDER_PROMPTS["ecom"])},
                        {"role": "user", "content": text or ""},
                    ],
                },
            )
            response.raise_for_status()
        raw_content = response.json()["message"]["content"]
        try:
            payload = json.loads(raw_content)
        except (TypeError, json.JSONDecodeError):
            payload = {"items": [], "confidence_score": 0}
        return _parse_result(payload, industry_type, self.provider_name)


class AnthropicMessagesLLMProvider(ILLMProvider):
    """Anthropic Messages API 的 HTTP Adapter；不使用任何供應商 SDK。"""

    provider_name = "anthropic"

    async def extract_order(
        self,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        industry_type: str = "ecom",
    ) -> ExtractionResult:
        settings = get_settings()
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY not configured")
        if not settings.llm_api_base or not settings.llm_model:
            raise RuntimeError("LLM_API_BASE and LLM_MODEL must be configured")
        content: List[dict] = [{"type": "text", "text": text or ""}]
        if image_url:
            content.append({"type": "image", "source": {"type": "url", "url": image_url}})
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                "{}/messages".format(settings.llm_api_base.rstrip("/")),
                headers={
                    "x-api-key": settings.llm_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "max_tokens": 1024,
                    "temperature": 0,
                    "system": _ORDER_PROMPTS.get(industry_type, _ORDER_PROMPTS["ecom"]),
                    "messages": [{"role": "user", "content": content}],
                },
            )
            response.raise_for_status()
        raw_content = response.json()["content"][0]["text"]
        try:
            payload = json.loads(raw_content)
        except (TypeError, json.JSONDecodeError):
            payload = {"items": [], "confidence_score": 0}
        return _parse_result(payload, industry_type, self.provider_name)
