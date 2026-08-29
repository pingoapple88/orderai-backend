"""Canonical T1 input must stay read-only, source-pinned, and synthetic."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "src/ui/contracts/orderai/orderai.canonical_module_input.json"
LOCALES = {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}


def test_canonical_module_input_is_pinned_read_only_and_synthetic() -> None:
    contract = json.loads(PATH.read_text(encoding="utf-8"))

    assert contract["canonicalInputVersion"] == "ORDERAI-CANONICAL-INPUT-W2-02"
    assert contract["moduleId"] == "orderai"
    assert contract["repository"] == "pingoapple88/orderai-backend"
    assert contract["branch"] == "feat/orderai-self-service-subscriptions"
    assert contract["sourceCommit"] == "133066f3b0544afb418b1fe2ad6fd5d962b43bf6"
    assert contract["parentCommit"] == contract["rollbackCommit"]
    assert contract["mode"] == "DEMO_MOCK"
    assert contract["availability"] == "available_synthetic"
    assert contract["integrationUse"] == "read_only_contract_and_local_fixture_only_no_live_fetch"
    assert set(contract["supportedLocales"]) == LOCALES
    assert contract["forbidden"] == {
        "liveFetch": True,
        "clientCompanyOrStoreAuthority": True,
        "rawPii": True,
        "paymentOrInvoiceCredentials": True,
        "newEvents": True,
    }


def test_canonical_routes_and_fixtures_cover_required_t1_input() -> None:
    contract = json.loads(PATH.read_text(encoding="utf-8"))
    routes = {item["route"]: item for item in contract["readOnlyRoutes"]}
    fixtures = {item["screenId"]: item for item in contract["fixtureCatalog"]}

    assert all(item["method"] == "GET" for item in routes.values())
    assert routes["/api/v1/orderai/subscriptions/status"]["errorOrBlocked"]["unknownPaymentOrInvoice"] == "manual_review"
    assert routes["/api/v1/orderai/subscriptions/usage"]["errorOrBlocked"]["unknownQuotaOrEntitlement"] == "manual_review"
    assert routes["/api/v1/orderai/subscriptions/invoices"]["errorOrBlocked"]["unknownInvoice"] == "manual_review"
    assert {"orderai.parse_result", "orderai.risk_review", "orderai.queue", "orderai.subscription_lifecycle"}.issubset(fixtures)
    assert fixtures["orderai.payment_method_management"]["availability"] == "owner_gate"
    assert all(item["mode"] == "DEMO_MOCK" for item in fixtures.values())


def test_canonical_input_has_explicit_owner_gates() -> None:
    contract = json.loads(PATH.read_text(encoding="utf-8"))
    statuses = {item["capability"]: item["status"] for item in contract["explicitlyPlannedOrBlocked"]}

    assert statuses["T1 visual route mounting"] == "PLANNED"
    assert statuses["formal OAuth"] == "BLOCKED"
    assert statuses["formal payment and payment method operations"] == "BLOCKED"
    assert statuses["formal invoice credential／tax"] == "BLOCKED"
    assert statuses["database write or runtime verification"] == "BLOCKED"
