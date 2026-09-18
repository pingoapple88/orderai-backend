"""Issue #39 focused tests: all inputs are synthetic and no provider performs I/O."""
import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.core.interfaces.erp_ingest import (
    ErpIngestBlockedError,
    PendingOrderContent,
    PendingOrderIntent,
    PendingOrderItem,
    PendingOrderMappingConfig,
)
from app.providers import (
    get_jiezhou_erp_ingest_provider,
    get_jiezhou_pending_order_mapping_config,
    settings,
)
from app.providers.erp_blocked import BlockedErpIngestProvider
from app.providers.jiezhou_erp import FakeJiezhouErpIngestProvider, JiezhouBlockedErpIngestProvider

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "jiezhou_pending_order_contract_v1.json"


def _fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text())


def _config_and_intent() -> tuple[PendingOrderMappingConfig, PendingOrderIntent]:
    data = _fixture()
    mapping = data["mapping_config"]
    raw_intent = data["intent"]
    content = raw_intent["content"]
    config = PendingOrderMappingConfig(**mapping)
    intent = PendingOrderIntent(
        tenant_id=raw_intent["tenant_id"],
        company_id=raw_intent["company_id"],
        sales_location_id=raw_intent["sales_location_id"],
        source_event_id=raw_intent["source_event_id"],
        content=PendingOrderContent(
            buyer_name=content["buyer_name"],
            buyer_contact_reference=content["buyer_contact_reference"],
            requested_for=content["requested_for"],
            special_request=content["special_request"],
            items=[PendingOrderItem(**item) for item in content["items"]],
        ),
        product_mapping=raw_intent["product_mapping"],
        idempotency_key=raw_intent["idempotency_key"],
        audit_reference=raw_intent["audit_reference"],
    )
    return config, intent


def test_jiezhou_factory_defaults_to_generic_blocked_provider(monkeypatch):
    monkeypatch.setattr(settings, "jiezhou_erp_ingest_provider", "blocked")
    provider = get_jiezhou_erp_ingest_provider()
    assert isinstance(provider, BlockedErpIngestProvider)


def test_jiezhou_mode_missing_required_settings_stays_blocked(monkeypatch):
    monkeypatch.setattr(settings, "jiezhou_erp_ingest_provider", "jiezhou")
    monkeypatch.setattr(settings, "jiezhou_tenant_id", 0)
    monkeypatch.setattr(settings, "jiezhou_company_id", 0)
    monkeypatch.setattr(settings, "jiezhou_sales_location_id", 0)
    monkeypatch.setattr(settings, "jiezhou_product_mapping_json", "{}")
    monkeypatch.setattr(settings, "jiezhou_contract_reference", "")

    provider = get_jiezhou_erp_ingest_provider()
    assert isinstance(provider, JiezhouBlockedErpIngestProvider)
    _, intent = _config_and_intent()
    with pytest.raises(ErpIngestBlockedError) as exc:
        asyncio.run(provider.submit_pending_confirmation_intent(intent))
    assert exc.value.reason_code == "ERP_CONNECTION_BLOCKED"


def test_jiezhou_mode_with_all_non_secret_settings_is_still_formally_blocked(monkeypatch):
    monkeypatch.setattr(settings, "jiezhou_erp_ingest_provider", "jiezhou")
    monkeypatch.setattr(settings, "jiezhou_tenant_id", 41001)
    monkeypatch.setattr(settings, "jiezhou_company_id", 42001)
    monkeypatch.setattr(settings, "jiezhou_sales_location_id", 43001)
    monkeypatch.setattr(settings, "jiezhou_product_mapping_json", '{"synthetic-product-a":"jiezhou-product-a"}')
    monkeypatch.setattr(settings, "jiezhou_contract_reference", "jiezhou-synthetic-contract-v1")

    assert get_jiezhou_pending_order_mapping_config().readiness_reason() is None
    provider = get_jiezhou_erp_ingest_provider()
    assert isinstance(provider, JiezhouBlockedErpIngestProvider)
    _, intent = _config_and_intent()
    with pytest.raises(ErpIngestBlockedError) as exc:
        asyncio.run(provider.submit_pending_confirmation_intent(intent))
    assert exc.value.reason_code == "ERP_CONNECTION_BLOCKED"


def test_fake_creates_pending_and_deduplicates_same_idempotency_key():
    config, intent = _config_and_intent()
    provider = FakeJiezhouErpIngestProvider(mapping_config=config)

    first = asyncio.run(provider.submit_pending_confirmation_intent(intent))
    replay = asyncio.run(provider.submit_pending_confirmation_intent(intent))

    assert first.status == replay.status == "pending"
    assert first.reference == replay.reference
    assert first.provider == "jiezhou_fake"
    assert len(provider.recorded_intents) == 1
    assert provider.transaction_side_effects == ()


@pytest.mark.parametrize(
    ("replacement", "reason_code"),
    [
        ("missing_mapping", "ERP_PRODUCT_MAPPING_MISSING"),
        ("wrong_company", "ERP_COMPANY_SCOPE_MISMATCH"),
        ("wrong_location", "ERP_SALES_LOCATION_SCOPE_MISMATCH"),
    ],
)
def test_fake_routes_missing_mapping_and_scope_mismatch_to_manual_review(replacement, reason_code):
    config, intent = _config_and_intent()
    if replacement == "missing_mapping":
        intent = replace(intent, product_mapping={})
    elif replacement == "wrong_company":
        intent = replace(intent, company_id=intent.company_id + 1)
    else:
        intent = replace(intent, sales_location_id=intent.sales_location_id + 1)

    result = asyncio.run(FakeJiezhouErpIngestProvider(config).submit_pending_confirmation_intent(intent))

    assert result.status == "manual_review"
    assert result.reason_code == reason_code
    assert result.reference.startswith("jz-manual-")


@pytest.mark.parametrize(
    ("synthetic_outcome", "reason_code"),
    [("timeout", "ERP_TIMEOUT"), ("unknown", "ERP_UNKNOWN_RESPONSE")],
)
def test_fake_routes_timeout_and_unknown_to_manual_review(synthetic_outcome, reason_code):
    config, intent = _config_and_intent()
    provider = FakeJiezhouErpIngestProvider(
        mapping_config=config,
        outcome_by_source_event={intent.source_event_id: synthetic_outcome},
    )

    result = asyncio.run(provider.submit_pending_confirmation_intent(intent))

    assert result.status == "manual_review"
    assert result.reason_code == reason_code
    assert provider.transaction_side_effects == ()
    assert len(provider.recorded_intents) == 1


def test_synthetic_fixture_uses_only_neutral_pending_fields_and_no_formal_transaction_fields():
    data = _fixture()
    serialized = json.dumps(data, sort_keys=True)
    for forbidden in ("payment", "inventory", "shipment", "invoice", "formal_order"):
        assert forbidden not in serialized
    assert data["fixture_version"] == "jiezhou-pending-order-synthetic-v1"
    assert data["contract_status"] == "[TODO: 待人工確認]"
    assert set(data["intent"]["content"]) == {
        "buyer_name",
        "buyer_contact_reference",
        "requested_for",
        "special_request",
        "items",
    }
