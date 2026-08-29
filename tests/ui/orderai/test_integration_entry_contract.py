"""Single T5 integration fixture only indexes verified local-only OrderAI states."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "src/ui/contracts/orderai/orderai.integration_entry.json"
FIXTURE_PATH = ROOT / "src/ui/fixtures/orderai/orderai_integration_entry.json"
LOCALES = {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}


def test_integration_entry_contract_keeps_one_local_only_baseline() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["screenContractVersion"] == "ORDERAI-INTEGRATION-W2-07"
    assert contract["screenId"] == "orderai.integration_entry"
    assert contract["dataBoundary"] == "DEMO_MOCK"
    assert contract["formalConnection"] is False
    assert set(contract["supportedLocales"]) == LOCALES
    baseline = contract["integrationBaseline"]
    assert baseline["subscriptionLifecycle"]["reuseMode"] == "REUSE_AS_IS"
    assert baseline["operationsReadiness"]["reuseMode"] == "REUSE_AS_IS"
    assert baseline["paymentMethodManagement"] == {
        "reuseMode": "INTEGRATE_VIA_ADAPTER",
        "screenId": "orderai.payment_method_management",
        "contractVersion": "ORDERAI-PAYMENT-METHOD-W2-02",
        "availability": "owner_gate",
    }
    assert baseline["smartAgricultureExpo"] == {
        "reuseMode": "INTEGRATE_VIA_ADAPTER",
        "screenId": "orderai.smart_agri_expo",
        "contractVersion": "ORDERAI-SMART-AGRI-EXPO-W2-01",
        "availability": "available_synthetic",
    }
    assert baseline["parseResult"] == {"reuseMode": "REUSE_AS_IS", "screenId": "orderai.parse_result", "contractVersion": "ORDERAI-PARSE-RESULT-W2-01"}
    assert baseline["riskReview"] == {"reuseMode": "REUSE_AS_IS", "screenId": "orderai.risk_review", "contractVersion": "ORDERAI-RISK-REVIEW-W2-01"}
    assert baseline["queue"] == {"reuseMode": "REUSE_AS_IS", "screenId": "orderai.queue", "contractVersion": "ORDERAI-QUEUE-W2-01"}
    assert baseline["canonicalModuleInput"] == {
        "reuseMode": "REUSE_AS_IS",
        "contractPath": "src/ui/contracts/orderai/orderai.canonical_module_input.json",
        "contractVersion": "ORDERAI-CANONICAL-INPUT-W2-02",
        "availability": "available_synthetic",
    }
    assert "smart_agriculture_expo" in contract["requiredViews"]
    assert {"parse_result", "risk_review", "queue"}.issubset(contract["requiredViews"])
    assert contract["invoiceCredentialBoundary"] == {
        "providerInterface": "IInvoiceProvider.issue",
        "publicStatusOnly": True,
        "credentialAccess": "owner_gate",
        "unknownResult": "manual_review",
        "forbiddenPublicFields": ["reference", "credential", "downloadUrl", "providerPayload"],
    }
    assert contract["eventBoundary"] == {"newEvents": [], "subscriptionEvents": [], "mode": "no_new_event"}


def test_integration_fixture_covers_five_locales_and_fail_closed_paths() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixtureVersion"] == "ORDERAI-INTEGRATION-FIXTURE-W2-07"
    assert fixture["dataBoundary"] == "DEMO_MOCK"
    assert fixture["formalConnection"] is False
    scenarios = fixture["scenarios"]
    assert {scenario["locale"] for scenario in scenarios} == LOCALES
    assert {scenario.get("channel") for scenario in scenarios} == {"direct", "dealer", "enterprise"}
    by_id = {scenario["id"]: scenario for scenario in scenarios}
    assert by_id["enterprise-invoice-manual-review"]["paymentStatus"] == "unknown"
    assert by_id["enterprise-invoice-manual-review"]["entitlementStatus"] == "manual_review"
    assert by_id["dealer-active-quota-and-billing"]["invoiceCredentialStatus"] == "owner_gate"
    assert by_id["enterprise-invoice-manual-review"]["invoiceCredentialStatus"] == "manual_review"
    assert by_id["parse-risk-review-required"]["riskStatus"] == "needs_review"
    assert by_id["queue-provider-timeout-dead-letter"]["queueStatus"] == "dead_letter"
    assert all("companyId" not in scenario and "paymentToken" not in scenario for scenario in scenarios)
