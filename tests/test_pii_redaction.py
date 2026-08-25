from __future__ import annotations

import asyncio

from app.providers import http_chat_llm
from app.services.pii_redaction import redact_pii


def test_redact_pii_actual_llm_input_and_audit_safe_summary(monkeypatch):
    original = "我是王小明，電話 0912-345-678，信箱 wang@example.com，身分證 A123456789，蘋果 2 顆"
    redacted = redact_pii(original)
    assert redacted == "我是[REDACTED_NAME]，電話 [REDACTED_PHONE]，信箱 [REDACTED_EMAIL]，身分證 [REDACTED_ID]，蘋果 2 顆"

    captured = {}

    class _Response:
        def json(self):
            return {"choices": [{"message": {"content": '{"items": [], "confidence_score": 0.0}'}}]}

    async def _fake_post(client, url, *, headers=None, payload, max_retries):
        captured["url"] = url
        captured["payload"] = payload
        captured["max_retries"] = max_retries
        return _Response()

    monkeypatch.setattr(http_chat_llm, "_post_json", _fake_post)
    provider = http_chat_llm.OpenAICompatibleLLMProvider(
        api_key="test-key",
        api_base="https://example.invalid/v1",
        model="test-model",
        temperature=0.2,
        max_retries=2,
    )
    asyncio.run(provider.extract_order(text=original))

    actual_llm_input = captured["payload"]["messages"][1]["content"][0]["text"]
    assert actual_llm_input == redacted
    assert "0912-345-678" not in actual_llm_input
    assert "wang@example.com" not in actual_llm_input
    assert "王小明" not in actual_llm_input
    assert captured["payload"]["temperature"] == 0.2
    assert captured["max_retries"] == 2
