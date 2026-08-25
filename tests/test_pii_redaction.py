from __future__ import annotations

import asyncio

import pytest

from app.providers import http_chat_llm
from app.services.pii_redaction import redact_pii


PII_FIXTURES = [
    ("zh-TW", "我是王小明，電話 0912-345-678，信箱 wang@example.com，身分證 A123456789，蘋果 2 顆", ["王小明", "0912-345-678", "wang@example.com", "A123456789"]),
    ("en", "My name is Alice Smith, phone +1 415 555 1212, email alice@example.com, apples 2", ["Alice Smith", "+1 415 555 1212", "alice@example.com"]),
    ("th", "ชื่ิอ สมชาย ใจดี โทร +66 81 234 5678 อีเมล somchai@example.com แอปเปิล 2", ["สมชาย ใจดี", "+66 81 234 5678", "somchai@example.com"]),
    ("ja", "名前：山田太郎 電話 +81 90 1234 5678 メール yamada@example.com りんご 2", ["山田太郎", "+81 90 1234 5678", "yamada@example.com"]),
    ("id", "Nama: Budi Santoso, telepon +62 812 3456 7890, email budi@example.com, apel 2", ["Budi Santoso", "+62 812 3456 7890", "budi@example.com"]),
]


@pytest.mark.parametrize("locale,original,forbidden", PII_FIXTURES)
def test_redact_pii_five_locale_fixtures(locale, original, forbidden):
    redacted = redact_pii(original)
    assert "[REDACTED_" in redacted, locale
    for raw in forbidden:
        assert raw not in redacted, locale


def test_redact_pii_actual_llm_input_and_audit_safe_summary(monkeypatch):
    original = PII_FIXTURES[0][1]
    redacted = redact_pii(original)
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
    for raw in PII_FIXTURES[0][2]:
        assert raw not in actual_llm_input
    assert captured["payload"]["temperature"] == 0.2
    assert captured["max_retries"] == 2
