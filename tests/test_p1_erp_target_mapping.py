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
