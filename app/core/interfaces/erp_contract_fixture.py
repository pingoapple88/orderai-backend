"""Strict, provider-neutral validation for synthetic pending-order contract fixtures.

This module is deliberately limited to local mappings already read by a caller.  It
opens no files, imports no settings, and has no provider, endpoint, authentication,
or transport dependency.  Both existing and future ERP fakes can use it to reject
fixture shape drift before constructing a ``PendingOrderIntent``.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.core.interfaces.erp_ingest import (
    PendingOrderContent,
    PendingOrderIntent,
    PendingOrderItem,
    PendingOrderMappingConfig,
)


SYNTHETIC_CONTRACT_STATUS = "[TODO: 待人工確認]"

_TOP_LEVEL_KEYS = frozenset({"fixture_version", "contract_status", "mapping_config", "intent"})
_MAPPING_CONFIG_KEYS = frozenset(
    {"tenant_id", "company_id", "sales_location_id", "product_mapping", "contract_reference"}
)
_INTENT_KEYS = frozenset(
    {
        "tenant_id",
        "company_id",
        "sales_location_id",
        "source_event_id",
        "content",
        "product_mapping",
        "idempotency_key",
        "audit_reference",
    }
)
_CONTENT_KEYS = frozenset(
    {"buyer_name", "buyer_contact_reference", "requested_for", "special_request", "items"}
)
_ITEM_KEYS = frozenset({"source_product_key", "product_name", "quantity", "unit"})
_TRANSACTIONAL_FIELD_NAMES = frozenset({"payment", "inventory", "shipment", "invoice", "formal_order"})


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_exact_keys(value: Any, expected_keys: frozenset[str]) -> Mapping[str, Any]:
    if not _is_mapping(value):
        raise ValueError("ERP_FIXTURE_SCHEMA_INVALID")
    keys = set(value)
    if keys & _TRANSACTIONAL_FIELD_NAMES:
        raise ValueError("ERP_FIXTURE_TRANSACTION_FIELD_FORBIDDEN")
    if keys != expected_keys:
        raise ValueError("ERP_FIXTURE_SCHEMA_INVALID")
    return value


def _require_nonempty_string(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ERP_FIXTURE_SCHEMA_INVALID")
    return value


def _require_optional_string(value: Any) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError("ERP_FIXTURE_SCHEMA_INVALID")
    return value


def _require_positive_integer(value: Any) -> int:
    if not _is_integer(value) or value <= 0:
        raise ValueError("ERP_FIXTURE_SCHEMA_INVALID")
    return value


def _require_string_mapping(value: Any) -> dict[str, str]:
    if not _is_mapping(value) or not value:
        raise ValueError("ERP_FIXTURE_SCHEMA_INVALID")
    normalized: dict[str, str] = {}
    for key, mapped_value in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("ERP_FIXTURE_SCHEMA_INVALID")
        normalized[key] = _require_nonempty_string(mapped_value)
    return normalized


def _require_items(value: Any) -> list[PendingOrderItem]:
    if not isinstance(value, list) or not value:
        raise ValueError("ERP_FIXTURE_SCHEMA_INVALID")
    items: list[PendingOrderItem] = []
    for item in value:
        raw_item = _require_exact_keys(item, _ITEM_KEYS)
        items.append(
            PendingOrderItem(
                source_product_key=_require_nonempty_string(raw_item["source_product_key"]),
                product_name=_require_nonempty_string(raw_item["product_name"]),
                quantity=_require_positive_integer(raw_item["quantity"]),
                unit=_require_nonempty_string(raw_item["unit"]),
            )
        )
    return items


def build_synthetic_pending_order_contract(
    fixture: Mapping[str, Any],
) -> tuple[PendingOrderMappingConfig, PendingOrderIntent]:
    """Validate one local synthetic fixture and construct neutral contract types.

    Validation is strict: every nesting level has an allowlist, transactional-field
    names are rejected explicitly, the fixture must retain the pending human-review
    marker, and scope/mapping must validate before a fake can run.  All failures use
    controlled error codes and never include raw fixture values.
    """

    raw_fixture = _require_exact_keys(fixture, _TOP_LEVEL_KEYS)
    fixture_version = _require_nonempty_string(raw_fixture["fixture_version"])
    if "synthetic" not in fixture_version.lower():
        raise ValueError("ERP_FIXTURE_NOT_SYNTHETIC")
    if raw_fixture["contract_status"] != SYNTHETIC_CONTRACT_STATUS:
        raise ValueError("ERP_FIXTURE_CONTRACT_STATUS_INVALID")

    raw_config = _require_exact_keys(raw_fixture["mapping_config"], _MAPPING_CONFIG_KEYS)
    config = PendingOrderMappingConfig(
        tenant_id=_require_positive_integer(raw_config["tenant_id"]),
        company_id=_require_positive_integer(raw_config["company_id"]),
        sales_location_id=_require_positive_integer(raw_config["sales_location_id"]),
        product_mapping=_require_string_mapping(raw_config["product_mapping"]),
        contract_reference=_require_nonempty_string(raw_config["contract_reference"]),
    )

    raw_intent = _require_exact_keys(raw_fixture["intent"], _INTENT_KEYS)
    raw_content = _require_exact_keys(raw_intent["content"], _CONTENT_KEYS)
    intent = PendingOrderIntent(
        tenant_id=_require_positive_integer(raw_intent["tenant_id"]),
        company_id=_require_positive_integer(raw_intent["company_id"]),
        sales_location_id=_require_positive_integer(raw_intent["sales_location_id"]),
        source_event_id=_require_nonempty_string(raw_intent["source_event_id"]),
        content=PendingOrderContent(
            buyer_name=_require_optional_string(raw_content["buyer_name"]),
            buyer_contact_reference=_require_optional_string(raw_content["buyer_contact_reference"]),
            requested_for=_require_optional_string(raw_content["requested_for"]),
            special_request=_require_optional_string(raw_content["special_request"]),
            items=_require_items(raw_content["items"]),
        ),
        product_mapping=_require_string_mapping(raw_intent["product_mapping"]),
        idempotency_key=_require_nonempty_string(raw_intent["idempotency_key"]),
        audit_reference=_require_nonempty_string(raw_intent["audit_reference"]),
    )

    validation_reason = config.validation_reason(intent)
    if validation_reason:
        raise ValueError(validation_reason)
    return config, intent


__all__ = ["SYNTHETIC_CONTRACT_STATUS", "build_synthetic_pending_order_contract"]
