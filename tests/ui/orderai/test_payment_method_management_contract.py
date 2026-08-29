"""Payment-method demo assets must remain owner-gated and free of payment credentials."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "src/ui/contracts/orderai/orderai.payment_method_management.json"
FIXTURE_PATH = ROOT / "src/ui/fixtures/orderai/orderai_payment_method_management.json"
LOCALES = {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
OWNER_GATED_ACTIONS = {
    "add_payment_method",
    "switch_default_payment_method",
    "update_payment_method_settings",
    "reauthorize_payment_method",
    "detach_payment_method",
    "remove_payment_method",
}


def test_payment_method_contract_is_provider_neutral_and_owner_gated() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["screenContractVersion"] == "ORDERAI-PAYMENT-METHOD-W2-02"
    assert contract["dataBoundary"] == "DEMO_MOCK"
    assert contract["formalConnection"] is False
    assert set(contract["supportedLocales"]) == LOCALES
    assert contract["providerBoundary"] == {
        "requiredAdapter": "IPaymentProvider",
        "existingCapabilities": ["create_payment", "get_status"],
        "paymentMethodVault": "owner_gate",
    }
    assert set(contract["actions"]) == OWNER_GATED_ACTIONS | {"view_payment_methods"}
    assert contract["actions"]["view_payment_methods"] == "available_synthetic"
    assert {status for action, status in contract["actions"].items() if action != "view_payment_methods"} == {"owner_gate"}
    assert contract["failClosed"]["unknownProvider"] == "manual_review"
    assert contract["failClosed"]["reauthorizationTimeout"] == "manual_review"
    assert contract["failClosed"]["unknownDetachmentStatus"] == "manual_review"
    assert contract["failClosed"]["removeLastActiveMethod"] == "blocked"
    assert contract["safeSummary"] == {
        "permittedFields": ["methodCount", "defaultMethodStatus", "managementAvailability"],
        "forbiddenFields": ["paymentMethodId", "paymentToken", "cardNumber", "bankAccount", "providerReference"],
    }


def test_payment_method_fixture_is_synthetic_and_covers_five_locales() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixtureVersion"] == "ORDERAI-PAYMENT-METHOD-FIXTURE-W2-02"
    assert fixture["dataBoundary"] == "DEMO_MOCK"
    assert {scenario["locale"] for scenario in fixture["scenarios"]} == LOCALES
    assert {scenario["action"] for scenario in fixture["scenarios"]} == OWNER_GATED_ACTIONS | {"view_payment_methods"}
    assert all(scenario["allowedActions"] == [] for scenario in fixture["scenarios"])
    assert {scenario["status"] for scenario in fixture["scenarios"]} == {"available_synthetic", "owner_gate", "blocked", "manual_review"}
    assert all(
        "PAYMENT_METHOD" in scenario["reasonCode"]
        or scenario["reasonCode"] in {"LAST_ACTIVE_PAYMENT_METHOD", "SYNTHETIC_MASKED_SUMMARY_ONLY"}
        for scenario in fixture["scenarios"]
    )
    view_scenario = next(s for s in fixture["scenarios"] if s["id"] == "view-method-summary-synthetic")
    assert view_scenario["safeSummary"] == {
        "methodCount": 0,
        "defaultMethodStatus": "not_available",
        "managementAvailability": "owner_gate",
    }
