"""Focused tests for additive provider-neutral ERP traceability manifests."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from app.core.interfaces.erp_ingest import PendingOrderContent, PendingOrderIntent, PendingOrderItem, PendingOrderMappingConfig
from app.core.interfaces.erp_traceability import (
    CANONICAL_INTENT_VERSION,
    TRACE_MANIFEST_VERSION,
    PendingOrderTraceManifest,
    build_pending_order_trace_manifest,
    pending_order_trace_validation_reason,
    verify_pending_order_trace_manifest,
)
from scripts.jiezhou_contract_smoke import DEFAULT_FIXTURE_PATH, run_contract_smoke


def _config_and_intent() -> tuple[PendingOrderMappingConfig, PendingOrderIntent]:
    fixture = json.loads(Path(DEFAULT_FIXTURE_PATH).read_text())
    raw_intent = fixture["intent"]
    content = raw_intent["content"]
    return (
        PendingOrderMappingConfig(**fixture["mapping_config"]),
        PendingOrderIntent(
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
        ),
    )


def test_trace_manifest_is_deterministic_and_order_independent_for_known_neutral_fields():
    config, intent = _config_and_intent()
    multi_item_intent = replace(
        intent,
        content=replace(
            intent.content,
            items=[
                *intent.content.items,
                PendingOrderItem(
                    source_product_key="synthetic-product-b",
                    product_name="Synthetic Product B",
                    quantity=1,
                    unit="unit",
                ),
            ],
        ),
        product_mapping={
            "synthetic-product-b": "provider-product-b",
            **intent.product_mapping,
        },
    )
    reordered_intent = replace(
        multi_item_intent,
        content=replace(multi_item_intent.content, items=list(reversed(multi_item_intent.content.items))),
        product_mapping=dict(reversed(list(multi_item_intent.product_mapping.items()))),
    )

    manifest = build_pending_order_trace_manifest(multi_item_intent, contract_version=config.contract_reference)
    reordered_manifest = build_pending_order_trace_manifest(reordered_intent, contract_version=config.contract_reference)

    assert manifest == reordered_manifest
    assert manifest.manifest_version == TRACE_MANIFEST_VERSION
    assert manifest.canonical_intent_version == CANONICAL_INTENT_VERSION
    assert pending_order_trace_validation_reason(
        reordered_intent,
        contract_version=config.contract_reference,
        manifest=manifest,
    ) is None


def test_trace_manifest_rejects_a_different_provider_neutral_intent():
    config, intent = _config_and_intent()
    manifest = build_pending_order_trace_manifest(intent, contract_version=config.contract_reference)
    changed_intent = replace(
        intent,
        content=replace(
            intent.content,
            items=[replace(intent.content.items[0], quantity=intent.content.items[0].quantity + 1)],
        ),
    )

    assert pending_order_trace_validation_reason(
        changed_intent,
        contract_version=config.contract_reference,
        manifest=manifest,
    ) == "ERP_TRACE_INTENT_SHA256_MISMATCH"


@pytest.mark.parametrize(
    ("replacement", "expected_reason"),
    [
        ("contract_version", "ERP_TRACE_CONTRACT_VERSION_MISMATCH"),
        ("idempotency_key_sha256", "ERP_TRACE_IDEMPOTENCY_REFERENCE_MISMATCH"),
        ("audit_reference_sha256", "ERP_TRACE_AUDIT_REFERENCE_MISMATCH"),
        ("idempotency_audit_binding_sha256", "ERP_TRACE_IDEMPOTENCY_AUDIT_BINDING_MISMATCH"),
    ],
)
def test_trace_manifest_rejects_contract_and_opaque_reference_inconsistency(replacement, expected_reason):
    config, intent = _config_and_intent()
    manifest = build_pending_order_trace_manifest(intent, contract_version=config.contract_reference)
    altered = replace(manifest, **{replacement: "0" * 64 if replacement != "contract_version" else "other-v1"})

    assert pending_order_trace_validation_reason(
        intent,
        contract_version=config.contract_reference,
        manifest=altered,
    ) == expected_reason
    with pytest.raises(ValueError, match=expected_reason):
        verify_pending_order_trace_manifest(
            intent,
            contract_version=config.contract_reference,
            manifest=altered,
        )


def test_trace_manifest_requires_controlled_contract_and_both_opaque_references():
    config, intent = _config_and_intent()

    for incomplete, expected_reason in (
        (replace(intent, idempotency_key=""), "ERP_IDEMPOTENCY_KEY_MISSING"),
        (replace(intent, audit_reference=" "), "ERP_AUDIT_REFERENCE_MISSING"),
    ):
        with pytest.raises(ValueError, match=expected_reason):
            build_pending_order_trace_manifest(incomplete, contract_version=config.contract_reference)
    with pytest.raises(ValueError, match="ERP_TRACE_CONTRACT_VERSION_MISSING"):
        build_pending_order_trace_manifest(intent, contract_version=" ")


def test_smoke_trace_manifest_is_comparable_and_contains_no_raw_fixture_values():
    config, intent = _config_and_intent()
    evidence = run_contract_smoke()
    manifest = evidence["trace_manifest"]

    assert set(manifest) == {
        "manifest_version",
        "canonical_intent_version",
        "contract_version",
        "intent_sha256",
        "idempotency_key_sha256",
        "audit_reference_sha256",
        "idempotency_audit_binding_sha256",
    }
    assert manifest["contract_version"] == config.contract_reference
    assert all(len(manifest[key]) == 64 for key in manifest if key.endswith("sha256"))
    assert pending_order_trace_validation_reason(
        intent,
        contract_version=config.contract_reference,
        manifest=PendingOrderTraceManifest(**manifest),
    ) is None

    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    for raw_value in (
        intent.content.buyer_name,
        intent.content.buyer_contact_reference,
        intent.content.requested_for,
        intent.content.special_request,
        intent.source_event_id,
        intent.idempotency_key,
        intent.audit_reference,
        *intent.product_mapping.keys(),
        *intent.product_mapping.values(),
    ):
        assert raw_value not in serialized


def test_manifest_helper_does_not_change_legacy_provider_interface():
    """The helper accepts an intent independently; no provider API is extended."""

    assert PendingOrderTraceManifest.__module__ == "app.core.interfaces.erp_traceability"
