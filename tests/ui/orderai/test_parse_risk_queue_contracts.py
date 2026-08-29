"""Parse, risk-review, and queue demo assets must mirror existing fail-closed behavior."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LOCALES = {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
ASSETS = {
    "parse": (
        ROOT / "src/ui/contracts/orderai/orderai.parse_result.json",
        ROOT / "src/ui/fixtures/orderai/orderai_parse_result.json",
        "ORDERAI-PARSE-RESULT-W2-01",
        "ORDERAI-PARSE-RESULT-FIXTURE-W2-01",
    ),
    "risk": (
        ROOT / "src/ui/contracts/orderai/orderai.risk_review.json",
        ROOT / "src/ui/fixtures/orderai/orderai_risk_review.json",
        "ORDERAI-RISK-REVIEW-W2-01",
        "ORDERAI-RISK-REVIEW-FIXTURE-W2-01",
    ),
    "queue": (
        ROOT / "src/ui/contracts/orderai/orderai.queue.json",
        ROOT / "src/ui/fixtures/orderai/orderai_queue.json",
        "ORDERAI-QUEUE-W2-01",
        "ORDERAI-QUEUE-FIXTURE-W2-01",
    ),
}
FORBIDDEN_FIXTURE_KEYS = {"companyId", "storeId", "userId", "rawMessage", "customerName", "customerPhone", "customerEmail", "lineUserId", "replyToken", "paymentToken", "providerReference"}


def test_parse_risk_queue_contracts_are_local_only_and_scope_safe() -> None:
    for _, (contract_path, _, contract_version, _) in ASSETS.items():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        assert contract["screenContractVersion"] == contract_version
        assert contract["dataBoundary"] == "DEMO_MOCK"
        assert contract["formalConnection"] is False
        assert set(contract["supportedLocales"]) == LOCALES
        assert contract["scopeSource"] == "server_principal_only"
        assert contract["timeRule"] == "UTC_RFC3339_only"
        assert contract["eventBoundary"] == {"newEvents": [], "mode": "no_new_event"}


def test_parse_fixture_covers_high_low_unmatched_review_and_redaction() -> None:
    fixture = json.loads(ASSETS["parse"][1].read_text(encoding="utf-8"))
    by_id = {scenario["id"]: scenario for scenario in fixture["scenarios"]}
    assert fixture["fixtureVersion"] == ASSETS["parse"][3]
    assert {scenario["locale"] for scenario in fixture["scenarios"]} == LOCALES
    assert by_id["parse-approved-high-confidence"]["confidenceScore"] == 0.85
    assert by_id["parse-low-confidence-review"]["reasonCode"] == "confidence_below_threshold"
    assert by_id["parse-unmatched-item-review"]["reasonCode"] == "catalog_product_unmatched"
    assert by_id["parse-scope-blocked"]["parseStatus"] == "blocked"
    assert all("[REDACTED_" in scenario.get("redactedPreview", "[REDACTED_SAFE]") for scenario in fixture["scenarios"])


def test_risk_fixture_preserves_threshold_idempotency_and_audit_projection() -> None:
    fixture = json.loads(ASSETS["risk"][1].read_text(encoding="utf-8"))
    by_id = {scenario["id"]: scenario for scenario in fixture["scenarios"]}
    assert fixture["fixtureVersion"] == ASSETS["risk"][3]
    assert {scenario["locale"] for scenario in fixture["scenarios"]} == LOCALES
    assert by_id["risk-approved-threshold-boundary"]["riskStatus"] == "approved"
    assert by_id["risk-approved-threshold-boundary"]["idempotencyReference"] == "line_event_hash_only"
    assert by_id["risk-low-confidence-review"]["riskStatus"] == "needs_review"
    assert by_id["risk-unmatched-item-review"]["reasonCode"] == "catalog_product_unmatched"
    assert by_id["risk-provider-timeout"]["riskStatus"] == "needs_review"


def test_queue_fixture_preserves_limited_retry_dedup_dead_letter_and_safe_payloads() -> None:
    fixture = json.loads(ASSETS["queue"][1].read_text(encoding="utf-8"))
    by_id = {scenario["id"]: scenario for scenario in fixture["scenarios"]}
    assert fixture["fixtureVersion"] == ASSETS["queue"][3]
    assert {scenario["locale"] for scenario in fixture["scenarios"]} == LOCALES
    assert by_id["queue-dedup-duplicate"]["queueStatus"] == "duplicate"
    assert by_id["queue-limited-retry"]["queueAttempt"] == 1
    assert by_id["queue-limited-retry"]["retryLimit"] == 1
    assert by_id["queue-dead-letter-review"]["queueAttempt"] == 2
    assert by_id["queue-dead-letter-review"]["deadLetterAction"] == "manual_review_only"
    assert all(set(scenario).isdisjoint(FORBIDDEN_FIXTURE_KEYS) for scenario in fixture["scenarios"])
    assert all(scenario["allowedActions"] == [] for scenario in fixture["scenarios"])
