"""Smart-agriculture expo demo assets must stay synthetic, PII-free, and fail-closed."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "src/ui/contracts/orderai/orderai.smart_agri_expo.json"
FIXTURE_PATH = ROOT / "src/ui/fixtures/orderai/orderai_smart_agri_expo.json"
LOCALES = {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
FORBIDDEN_FIXTURE_KEYS = {
    "companyId",
    "storeId",
    "userId",
    "customerName",
    "customerPhone",
    "customerEmail",
    "lineUserId",
    "rawMessage",
    "paymentToken",
    "paymentReference",
    "providerReference",
    "invoiceCredential",
    "invoiceDownloadUrl",
    "cardNumber",
    "bankAccount",
}


def test_smart_agri_expo_contract_is_synthetic_and_fail_closed() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["screenContractVersion"] == "ORDERAI-SMART-AGRI-EXPO-W2-01"
    assert contract["dataBoundary"] == "DEMO_MOCK"
    assert contract["formalConnection"] is False
    assert set(contract["supportedLocales"]) == LOCALES
    assert contract["scopeSource"] == "server_principal_only"
    assert contract["providerBoundary"] == {
        "llm": "ILLMProvider_demo_mock_only",
        "payment": "IPaymentProvider_status_projection_only",
        "subscription": "ISubscriptionProvider_status_projection_only",
        "invoice": "IInvoiceProvider_status_projection_only",
    }
    assert contract["aiAndSupportBoundary"] == {
        "label": "DEMO_MOCK",
        "sourceData": "synthetic_only",
        "allowUnauthorizedPii": False,
        "autoPublishPromotion": False,
        "autoSendCustomerReply": False,
        "humanReviewRequired": True,
    }
    assert contract["failClosed"] == {
        "unknownParse": "needs_review",
        "belowRiskThreshold": "needs_review",
        "unknownPromotionSuggestion": "manual_review",
        "unknownFaqAnswer": "manual_review",
        "providerTimeout": "manual_review",
        "unknownPayment": "manual_review",
        "unknownInvoice": "manual_review",
        "unknownEntitlement": "manual_review",
        "missingScope": "blocked",
    }
    assert contract["eventBoundary"] == {"newEvents": [], "mode": "no_new_event"}


def test_smart_agri_expo_fixture_covers_five_locales_without_pii() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert fixture["fixtureVersion"] == "ORDERAI-SMART-AGRI-EXPO-FIXTURE-W2-01"
    assert fixture["dataBoundary"] == "DEMO_MOCK"
    assert fixture["formalConnection"] is False
    assert {scenario["locale"] for scenario in fixture["scenarios"]} == LOCALES
    assert {scenario["channel"] for scenario in fixture["scenarios"]} == {"direct", "dealer", "enterprise"}
    assert all(scenario["demoLabel"] == "DEMO_MOCK" for scenario in fixture["scenarios"])
    assert all(scenario["allowedActions"] == [] for scenario in fixture["scenarios"])
    assert all(set(scenario).isdisjoint(FORBIDDEN_FIXTURE_KEYS) for scenario in fixture["scenarios"])

    scenario_by_id = {scenario["id"]: scenario for scenario in fixture["scenarios"]}
    assert scenario_by_id["agri-group-buy-create-review"]["riskStatus"] == "needs_review"
    assert scenario_by_id["agri-near-expiry-promotion-review"]["autoPublish"] is False
    assert scenario_by_id["agri-faq-customer-service-review"]["autoSend"] is False
    assert scenario_by_id["agri-subscription-payment-invoice-entitlement"] == {
        "id": "agri-subscription-payment-invoice-entitlement",
        "locale": "id-ID",
        "channel": "dealer",
        "view": "plan_subscription_entitlement",
        "demoLabel": "DEMO_MOCK",
        "subscriptionStatus": "manual_review",
        "paymentStatus": "unknown",
        "entitlementStatus": "manual_review",
        "invoiceStatus": "manual_review",
        "invoiceCredentialStatus": "owner_gate",
        "allowedActions": [],
        "reasonCode": "SYNTHETIC_UNKNOWN_PAYMENT_REQUIRES_RECONCILIATION",
    }
