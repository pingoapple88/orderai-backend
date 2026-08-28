"""T5 subscription screen contract: all inputs are local synthetic display data."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "src/ui/contracts/orderai/orderai.subscription_lifecycle.json"
FIXTURE = ROOT / "src/ui/fixtures/orderai/orderai_subscription_lifecycle.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_subscription_screen_contract_is_locale_scoped_and_fail_closed():
    contract = _load(CONTRACT)
    assert contract["screenContractVersion"] == "ORDERAI-SUBSCRIPTION-W2-01"
    assert set(contract["supportedLocales"]) == {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
    assert contract["scopeSource"] == "server_principal_only"
    assert contract["currencyRule"] == "integer_minor_units_only"
    assert contract["timeRule"] == "UTC_RFC3339_only"
    assert contract["failClosed"] == {
        "unknownPayment": "manual_review",
        "unknownInvoice": "manual_review",
        "unknownSubscriptionAction": "manual_review",
        "missingScope": "blocked",
    }
    assert {"companyId", "storeId", "userId"}.issubset(contract["forbiddenClientFields"])


def test_subscription_fixture_covers_channels_lifecycle_and_unknown_fail_closed():
    fixture = _load(FIXTURE)
    scenarios = fixture["scenarios"]
    assert fixture["dataBoundary"] == "DEMO_MOCK"
    assert {item["channel"] for item in scenarios} == {"direct", "dealer", "enterprise"}
    assert {item["locale"] for item in scenarios} == {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
    timeout = next(item for item in scenarios if item["id"] == "enterprise-provider-timeout")
    assert timeout["paymentStatus"] == "unknown"
    assert timeout["subscriptionStatus"] == "manual_review"
    assert timeout["entitlementStatus"] == "blocked"
    assert timeout["allowedActions"] == []
    assert all("companyId" not in item and "storeId" not in item and "userId" not in item for item in scenarios)
