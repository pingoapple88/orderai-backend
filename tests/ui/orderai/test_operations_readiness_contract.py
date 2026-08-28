"""Day 61–90 readiness assets are local-only, five-locale, and fail closed."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "src/ui/contracts/orderai/orderai.operations_readiness.json"
FIXTURE_PATH = ROOT / "src/ui/fixtures/orderai/orderai_operations_readiness.json"
LOCALES = {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
PUBLISHED_EVENTS = ["order.created", "order.updated", "order.confirmed"]


def test_operations_readiness_contract_keeps_only_existing_event_mapping() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["screenContractVersion"] == "ORDERAI-OPERATIONS-W2-01"
    assert contract["dataBoundary"] == "DEMO_MOCK"
    assert set(contract["supportedLocales"]) == LOCALES
    assert contract["eventBusMapping"] == {
        "publishedEvents": PUBLISHED_EVENTS,
        "subscriptionEvents": [],
        "mode": "mapping_only",
    }
    assert contract["failClosed"]["unknownProvider"] == "manual_review"
    assert contract["failClosed"]["backupRecovery"] == "owner_gate"


def test_operations_fixture_is_local_only_and_never_claims_unknown_cost() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixtureVersion"] == "ORDERAI-OPERATIONS-FIXTURE-W2-01"
    assert fixture["dataBoundary"] == "DEMO_MOCK"
    assert set(fixture["supportedLocales"]) == LOCALES
    assert {item["scenarioId"] for item in fixture["scenarios"]} == {
        "local_sandbox_provider_ready",
        "unknown_provider_fails_closed",
    }
    for scenario in fixture["scenarios"]:
        assert scenario["usageAndCost"]["costMinor"] is None
        assert scenario["usageAndCost"]["costStatus"] == "manual_review"
        assert scenario["backupRecovery"] == {"status": "owner_gate", "dataBoundary": "no_production_data"}
        assert scenario["eventBus"]["publishedEvents"] == PUBLISHED_EVENTS
    unknown = next(item for item in fixture["scenarios"] if item["scenarioId"] == "unknown_provider_fails_closed")
    assert unknown["provider"]["status"] == "manual_review"
