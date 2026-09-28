"""Synthetic Wanjiaxiang P1 target mapping contract tests."""
from __future__ import annotations

import json

import pytest

from app.core.p1_erp_target_mapping import (
    P1ErpTargetMappingError,
    parse_p1_erp_target_mappings,
    resolve_p1_erp_target,
)

WJ_MAPPING = json.dumps(
    {
        "stores": {
            "101": {
                "local_company_id": 11,
                "target_company_id": 201,
                "sales_location_id": 101,
            },
            "102": {
                "local_company_id": 12,
                "target_company_id": 202,
                "sales_location_id": 102,
            },
        }
    }
)

WJ_UNIT_MAPPING = json.dumps(
    {
        "stores": {
            "103": {
                "unit_id": "synthetic-wj-unit-direct-001",
                "tenant_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "legal_entity_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                "local_company_id": 13,
                "target_company_id": 203,
                "sales_location_id": 103,
                "mapping_status": "SYNTHETIC_ONLY",
            }
        }
    }
)


def test_wanjiaxiang_store_mapping_resolves_external_company_and_location() -> None:
    target = resolve_p1_erp_target(
        store_id=101,
        local_company_id=11,
        mappings_json=WJ_MAPPING,
        fallback_target_company_id=77,
        fallback_sales_location_id=91,
    )

    assert target is not None
    assert target.target_company_id == 201
    assert target.sales_location_id == 101
    assert target.local_company_id == 11


def test_mapping_does_not_guess_another_company() -> None:
    with pytest.raises(P1ErpTargetMappingError, match="erp_target_mapping_company_mismatch"):
        resolve_p1_erp_target(
            store_id=101,
            local_company_id=12,
            mappings_json=WJ_MAPPING,
            fallback_target_company_id=77,
            fallback_sales_location_id=91,
        )


def test_mapping_missing_store_fails_closed() -> None:
    with pytest.raises(P1ErpTargetMappingError, match="erp_target_mapping_missing"):
        resolve_p1_erp_target(
            store_id=999,
            local_company_id=11,
            mappings_json=WJ_MAPPING,
            fallback_target_company_id=77,
            fallback_sales_location_id=91,
        )


def test_empty_mapping_preserves_legacy_fallback() -> None:
    target = resolve_p1_erp_target(
        store_id=5,
        local_company_id=11,
        mappings_json="{}",
        fallback_target_company_id=77,
        fallback_sales_location_id=91,
    )

    assert target is not None
    assert target.target_company_id == 77
    assert target.sales_location_id == 91


def test_invalid_mapping_fails_closed() -> None:
    with pytest.raises(P1ErpTargetMappingError, match="erp_target_mapping_invalid"):
        parse_p1_erp_target_mappings('{"stores": [1, 2]}')


def test_wanjiaxiang_unit_mapping_resolves_explicit_identity_scope() -> None:
    target = resolve_p1_erp_target(
        store_id=103,
        local_company_id=13,
        mappings_json=WJ_UNIT_MAPPING,
        fallback_target_company_id=77,
        fallback_sales_location_id=91,
        unit_id="synthetic-wj-unit-direct-001",
        tenant_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        legal_entity_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    )

    assert target is not None
    assert target.target_company_id == 203
    assert target.unit_id == "synthetic-wj-unit-direct-001"
    assert target.mapping_status == "SYNTHETIC_ONLY"


def test_wanjiaxiang_unit_mapping_rejects_identity_mismatch() -> None:
    with pytest.raises(P1ErpTargetMappingError, match="erp_target_mapping_legal_entity_mismatch"):
        resolve_p1_erp_target(
            store_id=103,
            local_company_id=13,
            mappings_json=WJ_UNIT_MAPPING,
            fallback_target_company_id=77,
            fallback_sales_location_id=91,
            unit_id="synthetic-wj-unit-direct-001",
            tenant_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            legal_entity_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        )


def test_wanjiaxiang_unit_context_disables_legacy_fallback() -> None:
    with pytest.raises(P1ErpTargetMappingError, match="erp_target_mapping_identity_missing"):
        resolve_p1_erp_target(
            store_id=103,
            local_company_id=13,
            mappings_json="{}",
            fallback_target_company_id=77,
            fallback_sales_location_id=91,
            unit_id="synthetic-wj-unit-direct-001",
        )
