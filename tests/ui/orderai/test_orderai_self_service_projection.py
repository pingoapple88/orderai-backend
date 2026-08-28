"""Focused tests for the local-only OrderAI self-service projection."""

import json
from pathlib import Path

from src.adapters.orderai_adapter import DEFAULT_LOCALE, SUPPORTED_LOCALES, OrderAIDemoAdapter
from src.ui.screens.orderai import OrderAIScreenRenderer


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "src" / "ui" / "fixtures" / "orderai" / "orderai_self_service_projection.json"
LOCALES = ROOT / "src" / "ui" / "locales" / "orderai" / "self_service"


def test_self_service_projection_reuses_safe_existing_public_shape_without_billing_authority():
    model = OrderAIDemoAdapter().self_service_model("en-US")

    assert model["projection_contract_version"] == "ORDERAI-SELF-SERVICE-PROJECTION-W2-01"
    assert model["screen_id"] == "orderai.self_service_entry"
    assert model["locale"] == "en-US"
    assert model["mode"] == "DEMO_MOCK"
    assert model["evidence_level"] == "MOCK"
    assert model["formal_connection"] is False
    assert [entry["channel"] for entry in model["data"]["channels"]] == ["direct", "dealer", "enterprise"]
    assert model["data"]["entitlement"]["status"] == "pending_activation"
    assert model["data"]["billing"] == {
        "payment_status": "not_connected",
        "payment_status_key": "orderai.self_service.billing.not_connected",
        "invoice_status": "not_available",
        "invoice_status_key": "orderai.self_service.invoice.not_available",
    }
    encoded = json.dumps(model, ensure_ascii=False).lower()
    assert not any(value in encoded for value in ("company_id", "store_id", "reply_token", "email", "phone", "address", "https://", "http://"))


def test_self_service_projection_has_complete_five_locale_labels_and_safe_default():
    expected_keys = set(json.loads((LOCALES / f"{DEFAULT_LOCALE}.json").read_text(encoding="utf-8")))
    assert {path.stem for path in LOCALES.glob("*.json")} == SUPPORTED_LOCALES
    for path in LOCALES.glob("*.json"):
        assert set(json.loads(path.read_text(encoding="utf-8"))) == expected_keys
    assert OrderAIDemoAdapter().self_service_model("zh-TW")["locale"] == DEFAULT_LOCALE


def test_self_service_renderer_is_local_only_and_keeps_channel_and_scope_labels():
    html = OrderAIScreenRenderer().render_self_service_entry("zh-Hant-TW")

    assert 'data-screen-id="orderai.self_service_entry"' in html
    assert "直接通路" in html and "經銷通路" in html and "企業通路" in html
    assert "由伺服器 principal 決定" in html
    assert "正式服務：未連接" in html
    assert 'data-action-id="orderai.start_synthetic_parse"' in html
    assert "http://" not in html and "https://" not in html
    assert "company_id" not in html and "store_id" not in html


def test_self_service_fixture_is_versioned_and_contains_only_integral_quota_samples():
    model = json.loads(FIXTURE.read_text(encoding="utf-8"))
    quota = model["data"]["ai_quota"]

    assert isinstance(quota["sample_used"], int) and not isinstance(quota["sample_used"], bool)
    assert isinstance(quota["sample_limit"], int) and not isinstance(quota["sample_limit"], bool)
    assert 0 <= quota["sample_used"] <= quota["sample_limit"]
