"""Demo-only OrderAI fixture contract; no network, provider, queue or database access."""
import json
import re
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "demo_orderai.json"
LOCALES = {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
REQUIRED_SCENARIOS = {
    "parse-success-086",
    "malformed-input",
    "risk-needs-review-084",
    "provider-error",
    "provider-timeout",
    "provider-timeout-dead-letter",
    "pii-redacted-payload",
    "empty-state",
}


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def test_fixture_is_demo_only_and_has_exactly_five_locales():
    fixture = _fixture()
    assert fixture["meta"]["demoOnly"] is True
    assert fixture["meta"]["dataClassification"] == "synthetic"
    assert set(fixture["meta"]["supportedLocales"]) == LOCALES
    assert set(fixture["localeLabels"]) == LOCALES
    for labels in fixture["localeLabels"].values():
        assert {"demoBadge", "parseAction", "retryAction", "backAction", "needsReview", "deadLetter"} <= set(labels)


def test_fixture_covers_required_safe_workflows_and_risk_boundaries():
    scenarios = {scenario["id"]: scenario for scenario in _fixture()["scenarios"]}
    assert set(scenarios) == REQUIRED_SCENARIOS
    assert scenarios["parse-success-086"]["risk"] == {
        "status": "approved", "riskScore": 0.86, "reasonCodes": []
    }
    assert scenarios["risk-needs-review-084"]["risk"]["riskScore"] == 0.84
    assert scenarios["risk-needs-review-084"]["risk"]["status"] == "needs_review"
    assert scenarios["provider-error"]["queue"]["retryable"] is True
    assert scenarios["provider-timeout"]["queue"]["nextScenarioId"] == "provider-timeout-dead-letter"
    assert scenarios["provider-timeout-dead-letter"]["queue"]["state"] == "dead_letter"
    assert scenarios["malformed-input"]["queue"]["state"] == "blocked"


def test_fixture_exposes_only_safe_minimal_display_data():
    fixture = _fixture()
    encoded = json.dumps(fixture, ensure_ascii=False)
    assert not re.search(r"https?://|www\.", encoded, flags=re.IGNORECASE)
    assert not re.search(r"\b\d{8,}\b|[\w.+-]+@[\w.-]+", encoded)
    forbidden_keys = {"companyId", "storeId", "userId", "replyToken", "unitPriceCents", "totalCents", "payment"}
    for scenario in fixture["scenarios"]:
        assert forbidden_keys.isdisjoint(scenario["privacy"]["payloadPreview"])
        assert all(item["quantity"] > 0 and isinstance(item["quantity"], int) for item in scenario["result"]["items"])
        assert "REDACTED_NAME" in scenario["privacy"]["payloadPreview"].get("messageText", "") or scenario["id"] != "pii-redacted-payload"
