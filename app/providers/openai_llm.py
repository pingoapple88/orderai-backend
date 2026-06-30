"""ILLMProvider 的 OpenAI 相容實作（集團守則：AI 服務可替換）。

PR-1 僅提供骨架；完整解析與 fail-closed 在 PR-3 實作。
不綁任何廠商 SDK，使用 httpx 呼叫相容端點（可指向自架 Ollama）。
"""
import json
from typing import List, Optional

import httpx

from app.core.config import get_settings
from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult, ILLMProvider

settings = get_settings()

_PROMPT = (
    "You are an order extraction assistant. Extract structured order data. "
    'Respond ONLY with strict JSON: {"customer_name": string|null, '
    '"customer_phone": string|null, "items":[{"product_name": string, '
    '"quantity": number, "unit_price": number}], "confidence_score": number 0..1}.'
)


class OpenAILLMProvider(ILLMProvider):
    async def extract_order(self, *, image_url: Optional[str] = None, text: Optional[str] = None) -> ExtractionResult:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY not configured")

        content: List[dict] = [{"type": "text", "text": text or "Extract the order from this image."}]
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.llm_api_base}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _PROMPT},
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

        items = [
            ExtractedItem(
                product_name=i.get("product_name", ""),
                quantity=int(i.get("quantity", 0)),
                unit_price=float(i.get("unit_price", 0)),
            )
            for i in parsed.get("items", [])
        ]
        return ExtractionResult(
            items=items,
            customer_name=parsed.get("customer_name"),
            customer_phone=parsed.get("customer_phone"),
            confidence_score=float(parsed.get("confidence_score", 0) or 0),
            raw=parsed,
        )
