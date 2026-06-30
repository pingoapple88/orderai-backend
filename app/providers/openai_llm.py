"""ILLMProvider 的 OpenAI 相容實作（PR-3：依 industry_type 切換 prompt）。

不綁廠商 SDK，使用 httpx；可指向自架 Ollama。回傳統一 ExtractionResult。
"""
from __future__ import annotations

import json
from typing import List, Optional

import httpx

from app.core.config import get_settings
from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult, ILLMProvider

settings = get_settings()

# 依產業切換 System Prompt；回傳 JSON 結構需可被統一正規化
_PROMPTS = {
    "ecom": (
        "You are an e-commerce order extraction assistant. "
        'Respond ONLY with strict JSON: {"customer_name": string|null, '
        '"customer_phone": string|null, "items":[{"product_name": string, '
        '"quantity": number, "unit_price": number}], "confidence_score": number 0..1}.'
    ),
    "beauty": (
        "You are a beauty-salon booking extraction assistant. "
        'Respond ONLY with strict JSON: {"customer_name": string|null, '
        '"customer_phone": string|null, "items":[{"service_name": string, '
        '"appointment_time": string|null, "staff_name": string|null, '
        '"price": number|null}], "confidence_score": number 0..1}.'
    ),
    "food": (
        "You are a food-stall order extraction assistant. "
        'Respond ONLY with strict JSON: {"customer_name": string|null, '
        '"customer_phone": string|null, "items":[{"product_name": string, '
        '"quantity": number, "unit_price": number}], "confidence_score": number 0..1}.'
    ),
}


def _normalize_items(industry_type: str, raw_items: list) -> List[ExtractedItem]:
    """把各產業的原始 item 正規化為統一 ExtractedItem，讓建單邏輯相容。"""
    items = []
    for i in raw_items:
        if industry_type == "beauty":
            items.append(ExtractedItem(
                product_name=i.get("service_name", ""),
                quantity=1,
                unit_price=int(i.get("price") or 0),
                appointment_time=i.get("appointment_time"),
                staff_name=i.get("staff_name"),
            ))
        else:  # ecom / food
            items.append(ExtractedItem(
                product_name=i.get("product_name", ""),
                quantity=int(i.get("quantity", 0) or 0),
                unit_price=int(i.get("unit_price", 0) or 0),
            ))
    return items


class OpenAILLMProvider(ILLMProvider):
    async def extract_order(
        self,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        industry_type: str = "ecom",
    ) -> ExtractionResult:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY not configured")

        prompt = _PROMPTS.get(industry_type, _PROMPTS["ecom"])
        content: List[dict] = [{"type": "text", "text": text or "Extract the order from this image."}]
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "{}/chat/completions".format(settings.llm_api_base),
                headers={"Authorization": "Bearer {}".format(settings.llm_api_key)},
                json={
                    "model": settings.llm_model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": content},
                    ],
                },
            )
            resp.raise_for_status()
            raw_text = resp.json()["choices"][0]["message"]["content"]

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed = {"items": [], "confidence_score": 0}

        return ExtractionResult(
            items=_normalize_items(industry_type, parsed.get("items", [])),
            customer_name=parsed.get("customer_name"),
            customer_phone=parsed.get("customer_phone"),
            confidence_score=float(parsed.get("confidence_score", 0) or 0),
            industry_type=industry_type,
            raw=parsed,
        )
