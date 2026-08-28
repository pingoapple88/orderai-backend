"""Focused harness for T5 OrderAI screen contracts; it performs no network or database calls."""

import json
import re
from pathlib import Path

import pytest

from src.adapters.orderai_adapter import (
    DEFAULT_LOCALE,
    SCREEN_IDS,
    SUPPORTED_LOCALES,
    OrderAIDemoAdapter,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = ROOT / "src" / "ui" / "fixtures" / "orderai" / "orderai_screen_scenarios.json"
CONTRACT_DIRECTORY = ROOT / "src" / "ui" / "contracts" / "orderai"
LOCALE_DIRECTORY = ROOT / "src" / "ui" / "locales" / "orderai"
FORBIDDEN_RUNTIME_TERMS = ("http://", "https://", "requests.", "httpx.", "urllib", "fetch(", "webhook")
FORBIDDEN_EXPOSED_KEYS = {"company_id", "companyId", "store_key", "storeId", "reply_token", "replyToken", "email", "phone", "address"}


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _walk(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)
    elif isinstance(value, str):
        yield value


def test_contracts_define_exactly_the_three_t5_screens():
    contracts = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in CONTRACT_DIRECTORY.glob("*.json")}
    assert set(contracts) == {"orderai.parse_result", "orderai.risk_review", "orderai.queue"}
    for model in contracts.values():
        assert model["screen_id"] in SCREEN_IDS
        assert model["feature_id"] == "orderai"
        assert model["mode"] == "DEMO_MOCK"
        assert model["evidence_level"] == "MOCK"
        assert set(model) >= {"screen_id", "feature_id", "locale", "mode", "evidence_level", "status", "title_key", "data", "actions", "error", "updated_at"}


def test_fixture_has_safe_five_locale_screen_models_and_required_states():
    fixture = _fixture()
    assert fixture["meta"]["contract_version"] == "ORDERAI-UI-W2-01"
    assert fixture["meta"]["formal_connection"] is False
    assert set(fixture["meta"]["supported_locales"]) == SUPPORTED_LOCALES
    scenarios = {scenario["scenario_id"]: scenario for scenario in fixture["scenarios"]}
    assert {"parse_success", "low_confidence_unmatched", "provider_timeout_retry", "dead_letter_manual_retry", "duplicate_event_blocked", "empty_state"} == set(scenarios)
    for scenario in scenarios.values():
        assert {model["screen_id"] for model in scenario["view_models"]} == SCREEN_IDS
        for model in scenario["view_models"]:
            assert model["mode"] == "DEMO_MOCK"
            assert model["evidence_level"] == "MOCK"
            assert model["audit_reference"].startswith("demo-audit-")
    review = next(model for model in scenarios["low_confidence_unmatched"]["view_models"] if model["screen_id"] == "orderai.risk_review")
    assert review["status"] == "needs_review"
    assert review["data"]["risk_score"] == 0.84
    assert review["data"]["unmatched_items"]
    approved = next(model for model in scenarios["parse_success"]["view_models"] if model["screen_id"] == "orderai.risk_review")
    assert approved["data"]["approval_state"] == "approved"
    assert approved["data"]["automatic_approval"] is True
    parsed = next(model for model in scenarios["parse_success"]["view_models"] if model["screen_id"] == "orderai.parse_result")
    assert parsed["data"]["input_summary"]
    assert any(action["id"] == "orderai.submit_synthetic_input" and action["result_state"] == "loading" for action in parsed["actions"])
    dead_letter = next(model for model in scenarios["dead_letter_manual_retry"]["view_models"] if model["screen_id"] == "orderai.queue")
    assert dead_letter["data"]["queue_state"] == "dead_letter"
    assert dead_letter["actions"] == [{"id": "orderai.manual_retry", "label_key": "orderai.action.manual_retry", "requires_confirmation": True}]


def test_adapter_normalizes_locale_and_never_accepts_company_scope():
    adapter = OrderAIDemoAdapter()
    assert adapter.normalize_locale("en-US") == "en-US"
    assert adapter.normalize_locale("zh-TW") == DEFAULT_LOCALE
    assert adapter.normalize_locale(None) == DEFAULT_LOCALE
    models = adapter.screen_models("parse_success", "ja-JP")
    assert {model["locale"] for model in models} == {"ja-JP"}
    encoded = json.dumps(models, ensure_ascii=False)
    assert not any(key in encoded for key in FORBIDDEN_EXPOSED_KEYS)
    with pytest.raises(KeyError):
        adapter.screen_models("unknown-scenario")


def test_amounts_quantities_and_queue_protection_are_fail_closed_display_values():
    for scenario in _fixture()["scenarios"]:
        for model in scenario["view_models"]:
            for item in model["data"].get("items", []):
                assert isinstance(item["quantity"], int) and item["quantity"] > 0
                assert isinstance(item["amount_minor"], int)
                assert not isinstance(item["amount_minor"], bool)
            if model["screen_id"] == "orderai.risk_review" and model["data"].get("approval_state") == "approved":
                assert model["data"]["risk_score"] > model["data"]["risk_threshold"]
                assert model["data"]["automatic_approval"] is True
            elif model["screen_id"] == "orderai.risk_review":
                assert model["data"]["automatic_approval"] is False
            if model["screen_id"] == "orderai.queue" and model["data"]["queue_state"] == "dead_letter":
                assert model["status"] == "blocked"


def test_locales_are_complete_and_fixture_is_redacted_without_runtime_connections():
    expected_keys = set(json.loads((LOCALE_DIRECTORY / "zh-Hant-TW.json").read_text(encoding="utf-8")))
    assert {path.stem for path in LOCALE_DIRECTORY.glob("*.json")} == SUPPORTED_LOCALES
    for path in LOCALE_DIRECTORY.glob("*.json"):
        assert set(json.loads(path.read_text(encoding="utf-8"))) == expected_keys
    encoded = json.dumps(_fixture(), ensure_ascii=False).lower()
    assert not any(term in encoded for term in FORBIDDEN_RUNTIME_TERMS)
    assert not re.search(r"[\w.+-]+@[\w.-]+|\b\d{8,}\b", encoded)
    assert not any(key.lower() in encoded for key in ("company_id", "store_key", "reply_token", "phone", "email", "address"))
