from __future__ import annotations

import asyncio

import pytest

from app.providers import http_chat_llm
from app.services import order_risk_service
from app.services.order_risk_service import RiskDecision
from app.services.pii_redaction import redact_pii


PII_FIXTURES = [
    ("zh-Hant-TW", "我是王小明，電話 0912-345-678，信箱 wang@example.com，身分證 A123456789，蘋果 2 顆", ["王小明", "0912-345-678", "wang@example.com", "A123456789"]),
    ("en-US", "My name is Alice Smith, phone +1 415 555 1212, email alice@example.com, apples 2", ["Alice Smith", "+1 415 555 1212", "alice@example.com"]),
    ("th-TH", "ชื่ิอ สมชาย ใจดี โทร +66 81 234 5678 อีเมล somchai@example.com แอปเปิล 2", ["สมชาย ใจดี", "+66 81 234 5678", "somchai@example.com"]),
    ("ja-JP", "名前：山田太郎 電話 +81 90 1234 5678 メール yamada@example.com りんご 2", ["山田太郎", "+81 90 1234 5678", "yamada@example.com"]),
    ("id-ID", "Nama: Budi Santoso, telepon +62 812 3456 7890, email budi@example.com, apel 2", ["Budi Santoso", "+62 812 3456 7890", "budi@example.com"]),
]


@pytest.mark.parametrize("locale,original,forbidden", PII_FIXTURES)
def test_redact_pii_five_locale_fixtures(locale, original, forbidden):
    redacted = redact_pii(original)
    assert "[REDACTED_" in redacted, locale
    for raw in forbidden:
        assert raw not in redacted, locale


@pytest.mark.parametrize("locale,original,forbidden", PII_FIXTURES)
def test_redact_pii_actual_llm_input_for_five_locales(monkeypatch, locale, original, forbidden):
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
    for raw in forbidden:
        assert raw not in actual_llm_input
    assert captured["payload"]["temperature"] == 0.2
    assert captured["max_retries"] == 2


@pytest.mark.parametrize("locale,original,forbidden", PII_FIXTURES)
def test_audit_uses_redact_before_hashing_for_five_locales(monkeypatch, locale, original, forbidden):
    captured = []
    calls = []
    real_redact = redact_pii

    class _Db:
        def add(self, item):
            captured.append(item)

        def commit(self):
            return None

    def _track_redact(value):
        calls.append(value)
        return real_redact(value)

    monkeypatch.setattr(order_risk_service, "redact_pii", _track_redact)
    order_risk_service.audit_ai_decision(
        _Db(),
        principal={"user_id": 1, "store_id": 2},
        extraction=None,
        decision=RiskDecision(status="needs_review", reasons=["synthetic"], threshold=0.85),
        source_text=original,
    )

    assert calls == [original], locale
    stored = captured[0].new_value
    assert set(stored) == {
        "status", "reason_codes", "threshold", "confidence_score", "provider", "item_count", "source_sha256"
    }
    for raw in forbidden:
        assert raw not in str(stored), locale
