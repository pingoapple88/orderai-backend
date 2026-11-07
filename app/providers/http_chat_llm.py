"""通用 HTTP LLM Adapter；模型與端點由 ENV 注入，業務層只依賴 ILLMProvider。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult, ILLMProvider
from app.services.pii_redaction import redact_pii


_ORDER_PROMPTS = {
    "ecom": """你是繁體中文訂單資料抽取器。僅抽取使用者原文中明確出現的客戶、商品與數量。
禁止補猜商品、數量、價格、單位、姓名或電話。使用者沒有明講的欄位必須回傳 null 或空陣列。
口語與語音轉寫（例：「我要兩盒蛋」「蛋給我來個兩盒」「那個蘋果三顆好了」）：
- 中文數字轉整數（一=1、兩/二=2、三=3…、十=10、十二=12、半打=6、一打=12），quantity 一律回整數。
- 量詞放 unit（盒、顆、份、杯、打），不可併進 product_name；「我要」「給我」「幫我訂」「好了」等語助詞不是商品。
- 「那個」「一樣的」「老樣子」等無法從原文確定的指涉 → 不抽該品項，並降低 confidence_score。
- 不確定的數量回 null，不要猜；evidence 保留原文片段（含中文數字原樣）。
- 若輸入是圖片：只抽取圖片中清楚可見的文字或手寫內容，看不清楚就回空陣列與低 confidence_score。
- 任何價格、金額一律不要回傳（價格由店家型錄決定）。
每個商品必須保留 evidence（原文對應片段）並提供 0 到 1 的 field_confidence。
只回傳 JSON：
{"customer_name": string|null, "customer_phone": string|null,
 "items": [{"product_name": string, "quantity": integer|null, "unit": string|null,
             "evidence": string, "field_confidence": number}],
 "confidence_score": number, "field_confidence": {"customer_name": number, "items": number}}
""",
    "food": """你是繁體中文餐飲訂單資料抽取器。僅抽取使用者原文中明確出現的客戶、餐點與數量。
禁止補猜餐點、數量、價格、加料或取餐資訊。沒有明講的欄位必須回傳 null 或空陣列。
口語與語音轉寫（例：「我要兩盒蛋」「蛋給我來個兩盒」「那個蘋果三顆好了」）：
- 中文數字轉整數（一=1、兩/二=2、三=3…、十=10、十二=12、半打=6、一打=12），quantity 一律回整數。
- 量詞放 unit（盒、顆、份、杯、打），不可併進 product_name；「我要」「給我」「幫我訂」「好了」等語助詞不是商品。
- 「那個」「一樣的」「老樣子」等無法從原文確定的指涉 → 不抽該品項，並降低 confidence_score。
- 不確定的數量回 null，不要猜；evidence 保留原文片段（含中文數字原樣）。
- 若輸入是圖片：只抽取圖片中清楚可見的文字或手寫內容，看不清楚就回空陣列與低 confidence_score。
- 任何價格、金額一律不要回傳（價格由店家型錄決定）。
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


# WO-L3-002 對話層①暖話：provider 產生 opening/closing 兩句（嚴禁數字，呼叫端另有正則把關）。
_COMPOSE_SCENE = {
    "order_created": "已成功收到一筆訂單",
    "needs_review": "這筆訂單需要轉店家人工確認",
    "provider_error": "系統暫時忙碌，已請店家協助",
}


def _compose_system(outcome: str, brand_voice: str) -> str:
    voice = (brand_voice or "").strip() or "親切、簡短有禮的台灣在地小農小店"
    scene = _COMPOSE_SCENE.get(outcome, "收到客人的訊息")
    return (
        "你是「{}」風格的 LINE 訂單小幫手。情境：{}。".format(voice, scene)
        + '只輸出 JSON：{"opening": string, "closing": string}。'
        + "opening 與 closing 各一句溫暖口語的話，各不超過 20 個字。"
        + "絕對不要出現任何數字、金額、品項名稱或數量（系統會自己帶）。"
    )


def _parse_compose(raw_content: str) -> tuple:
    """解析暖話 JSON → (opening, closing)；缺任一則上拋，由呼叫端 fail-safe 回退罐頭句。"""
    data = json.loads(raw_content)
    opening = str((data or {}).get("opening") or "").strip()
    closing = str((data or {}).get("closing") or "").strip()
    if not opening or not closing:
        raise ValueError("compose_reply returned empty opening/closing")
    return opening, closing


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

    async def compose_reply(self, outcome: str, brand_voice: str = "") -> tuple:
        """對話層①暖話：回 (opening, closing)。溫度較高取自然語氣；只回文字，不碰數字。"""
        if not self.api_key and not self.allow_empty_api_key:
            raise RuntimeError("LLM_API_KEY not configured")
        if not self.api_base or not self.model:
            raise RuntimeError("LLM_API_BASE and LLM_MODEL must be configured")
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
                    "temperature": 0.7,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _compose_system(outcome, brand_voice)},
                        {"role": "user", "content": "請產生 opening 與 closing。"},
                    ],
                },
                max_retries=self.max_retries,
            )
        return _parse_compose(response.json()["choices"][0]["message"]["content"])


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

    async def compose_reply(self, outcome: str, brand_voice: str = "") -> tuple:
        """對話層①暖話：回 (opening, closing)。"""
        if not self.api_base or not self.model:
            raise RuntimeError("LLM_API_BASE and LLM_MODEL must be configured")
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await _post_json(
                client,
                "{}/api/chat".format(self.api_base.rstrip("/")),
                payload={
                    "model": self.model,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.7},
                    "messages": [
                        {"role": "system", "content": _compose_system(outcome, brand_voice)},
                        {"role": "user", "content": "請產生 opening 與 closing。"},
                    ],
                },
                max_retries=self.max_retries,
            )
        return _parse_compose(response.json()["message"]["content"])


def _anthropic_image_source(image_url: str) -> dict:
    """WO-L3-003：LINE 圖片以 data URL 傳入（非公開 URL）；Messages 協定需拆成 base64 source。"""
    if image_url.startswith("data:") and ";base64," in image_url:
        header, data = image_url[5:].split(";base64,", 1)
        return {"type": "base64", "media_type": header or "image/jpeg", "data": data}
    return {"type": "url", "url": image_url}


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
            content.append({"type": "image", "source": _anthropic_image_source(image_url)})
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

    async def compose_reply(self, outcome: str, brand_voice: str = "") -> tuple:
        """對話層①暖話：回 (opening, closing)。"""
        if not self.api_key and not self.allow_empty_api_key:
            raise RuntimeError("LLM_API_KEY not configured")
        if not self.api_base or not self.model:
            raise RuntimeError("LLM_API_BASE and LLM_MODEL must be configured")
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
                    "max_tokens": 256,
                    "temperature": 0.7,
                    "system": _compose_system(outcome, brand_voice),
                    "messages": [{"role": "user", "content": "請產生 opening 與 closing。"}],
                },
                max_retries=self.max_retries,
            )
        return _parse_compose(response.json()["content"][0]["text"])
