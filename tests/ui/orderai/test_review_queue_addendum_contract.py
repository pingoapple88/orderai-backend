"""Consumer/owner review addendum stays synthetic, separated, and fail-closed."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONSUMER_CONTRACT = ROOT / "src/ui/contracts/orderai/orderai.consumer_conversation.json"
CONSUMER_FIXTURE = ROOT / "src/ui/fixtures/orderai/orderai_consumer_conversation.json"
QUEUE_CONTRACT = ROOT / "src/ui/contracts/orderai/orderai.review_queue.json"
QUEUE_FIXTURE = ROOT / "src/ui/fixtures/orderai/orderai_review_queue.json"
HANDOFF_CONTRACT = ROOT / "src/ui/contracts/orderai/orderai.confirmation_handoff.json"
HANDOFF_FIXTURE = ROOT / "src/ui/fixtures/orderai/orderai_confirmation_handoff.json"
LOCALES = {"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"}
CONSUMER_HIDDEN = {"confidenceScore", "threshold", "riskStatus", "queueStatus", "queueAttempt", "deadLetter", "erpFields", "providerPayload", "auditReference"}
SENSITIVE_KEYS = {"companyId", "storeId", "userId", "rawMessage", "customerName", "customerPhone", "customerEmail", "lineUserId", "paymentToken", "providerReference", "erpOrderId"}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_consumer_view_hides_owner_and_internal_fields() -> None:
    contract = _read(CONSUMER_CONTRACT)
    fixture = _read(CONSUMER_FIXTURE)
    assert contract["screenContractVersion"] == "ORDERAI-CONSUMER-CONVERSATION-W2-01"
    assert contract["dataBoundary"] == "DEMO_MOCK"
    assert contract["formalConnection"] is False
    assert set(contract["supportedLocales"]) == LOCALES
    assert set(contract["consumerHiddenFields"]) == CONSUMER_HIDDEN
    assert contract["draftBoundary"]["formalOrder"] is False
    assert contract["draftBoundary"]["automaticOrderCreation"] is False
    assert {scenario["locale"] for scenario in fixture["scenarios"]} == LOCALES
    for scenario in fixture["scenarios"]:
        assert set(scenario).isdisjoint(CONSUMER_HIDDEN | SENSITIVE_KEYS)
        assert scenario["draftNotice"]
        assert scenario["nextAction"]


def test_owner_review_queue_is_fail_closed_and_draft_only() -> None:
    contract = _read(QUEUE_CONTRACT)
    fixture = _read(QUEUE_FIXTURE)
    assert contract["confidenceThreshold"] == 0.85
    assert contract["statusMapping"]["confidenceBelowThreshold"] == "manual_review"
    assert contract["statusMapping"]["unknownResult"] == "manual_review"
    assert contract["reviewBoundary"] == {
        "formalOrderCreation": False,
        "saveDraftOnly": True,
        "automaticOrderCreation": False,
        "automaticApprovalForUnknown": False,
        "humanConfirmationOwner": "T2／中央 contract owner",
        "forbiddenActions": ["create_order", "send_to_erp", "submit_stallpay_order", "retry_provider"],
    }
    assert {scenario["locale"] for scenario in fixture["scenarios"]} == LOCALES
    by_id = {scenario["id"]: scenario for scenario in fixture["scenarios"]}
    assert by_id["review-low-confidence-manual-review"]["draftStatus"] == "manual_review"
    assert by_id["review-unknown-manual-review"]["draftStatus"] == "manual_review"
    assert {"stock_shortage", "pickup_conflict"}.issubset(by_id["review-shortage-and-conflict"]["reviewFlags"])
    for scenario in fixture["scenarios"]:
        assert "create_order" not in scenario["allowedActions"]
        assert "send_to_erp" not in scenario["allowedActions"]
        assert set(scenario).isdisjoint(SENSITIVE_KEYS)


def test_confirmation_handoff_remains_provider_neutral_and_blocked() -> None:
    contract = _read(HANDOFF_CONTRACT)
    fixture = _read(HANDOFF_FIXTURE)
    assert contract["availability"] == "BLOCKED"
    assert contract["formalConnection"] is False
    assert contract["endpoint"] == "[TODO: 待 T2／中央 contract owner 確認]"
    assert contract["httpMethod"] == "[TODO: 待 T2／中央 contract owner 確認]"
    assert contract["formalOrderCreation"] is False
    assert contract["requiredCrossTeamRequests"] == ["XREQ-EXPO-0002", "XREQ-EXPO-0003", "XREQ-EXPO-0005"]
    assert contract["fallback"] == {"status": "blocked", "action": "save_draft_only", "automaticOrderCreation": False, "automaticRetry": False}
    assert contract["forbidden"] == {"liveFetch": True, "formalOrderWrite": True, "erpWrite": True, "payment": True, "invoice": True, "newEvents": True}
    assert {scenario["locale"] for scenario in fixture["scenarios"]} == LOCALES
    assert all(scenario["draftStatus"] == "blocked" for scenario in fixture["scenarios"])
    assert all(scenario["nextAction"] == "save_draft_only" for scenario in fixture["scenarios"])
    assert all(set(scenario).isdisjoint(SENSITIVE_KEYS) for scenario in fixture["scenarios"])
