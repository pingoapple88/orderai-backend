"""Expo P0 handoff must be a complete, read-only, fail-closed synthetic input."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "src/ui/contracts/orderai/orderai.expo_p0_handoff.json"
FIXTURE_PATH = ROOT / "src/ui/fixtures/orderai/orderai_expo_p0_handoff.json"
LOCALES = {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
REQUIRED_SCENARIO_FIELDS = {
    "id", "screenId", "route", "inputFixture", "parsedOutput", "confidence", "threshold",
    "riskStatus", "humanAction", "fallback", "sourceCommit", "evidencePath", "rollback",
    "mode", "auditIntent", "idempotencyReference", "createdAt", "localeVariants",
    "scenarioTitleKey", "mobileDisplay", "demoMockBadge",
}
FORBIDDEN_FIXTURE_KEYS = {
    "companyId", "storeId", "userId", "rawMessage", "customerName", "customerPhone",
    "customerEmail", "lineUserId", "paymentToken", "providerReference", "invoiceCredential",
}


def test_expo_p0_handoff_contract_is_synthetic_scope_safe_and_fail_closed() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["screenContractVersion"] == "ORDERAI-EXPO-P0-HANDOFF-W2-01"
    assert contract["mode"] == "DEMO_MOCK"
    assert contract["availability"] == "available_synthetic"
    assert contract["formalConnection"] is False
    assert set(contract["supportedLocales"]) == LOCALES
    assert contract["scopeAndSafety"] == {
        "scopeSource": "server_principal_only",
        "timeRule": "UTC_RFC3339_only",
        "piiRedactionRequired": True,
        "auditIntent": "ai.order.decision",
        "idempotencySource": "server_derived_line_event_hash_only",
        "noAutomaticOrderCreate": True,
        "noAutomaticRetry": True,
        "newEvents": [],
    }
    assert contract["failClosed"] == {
        "confidenceThreshold": 0.85,
        "lowConfidence": "needs_review",
        "unknownResult": "manual_review",
        "missingTenantScope": "blocked",
        "providerTimeout": "manual_review",
    }
    assert contract["eventBoundary"] == {"newEvents": [], "mode": "no_new_event"}


def test_expo_p0_fixture_has_three_complete_safe_scenarios() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixtureVersion"] == "ORDERAI-EXPO-P0-HANDOFF-FIXTURE-W2-01"
    assert fixture["mode"] == "DEMO_MOCK"
    scenarios = {scenario["id"]: scenario for scenario in fixture["scenarios"]}
    assert set(scenarios) == {
        "expo-p0-high-confidence-success",
        "expo-p0-low-confidence-needs-review",
        "expo-p0-unknown-manual-review",
    }
    assert all(set(scenario) == REQUIRED_SCENARIO_FIELDS for scenario in scenarios.values())
    assert all(set(scenario).isdisjoint(FORBIDDEN_FIXTURE_KEYS) for scenario in scenarios.values())
    assert all(set(scenario["localeVariants"]) == LOCALES for scenario in scenarios.values())
    assert all(scenario["mobileDisplay"]["viewport"] == "390x844" for scenario in scenarios.values())
    assert all(scenario["demoMockBadge"] == "DEMO_MOCK" for scenario in scenarios.values())
    assert all(scenario["auditIntent"] == "ai.order.decision" for scenario in scenarios.values())
    assert all(scenario["idempotencyReference"] == "server_derived_line_event_hash_only" for scenario in scenarios.values())

    high = scenarios["expo-p0-high-confidence-success"]
    low = scenarios["expo-p0-low-confidence-needs-review"]
    unknown = scenarios["expo-p0-unknown-manual-review"]
    assert (high["confidence"], high["threshold"], high["riskStatus"]) == (0.85, 0.85, "approved")
    assert (low["confidence"], low["threshold"], low["riskStatus"]) == (0.84, 0.85, "needs_review")
    assert (unknown["confidence"], unknown["riskStatus"]) == (None, "manual_review")
    assert unknown["parsedOutput"]["status"] == "unknown"
    assert unknown["fallback"] == "manual_review_no_auto_retry_no_duplicate_order"
