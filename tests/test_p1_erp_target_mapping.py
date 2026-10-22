"""Synthetic Wanjiaxiang P1 target mapping contract tests."""
from __future__ import annotations

import json
from pathlib import Path

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

SYNTHETIC_MAPPING_FIXTURE = (
    Path(__file__).parent / "fixtures" / "wanjiaxiang_p1_mapping_synthetic_v1.json"
)


def _synthetic_mapping() -> dict:
    return json.loads(SYNTHETIC_MAPPING_FIXTURE.read_text(encoding="utf-8"))


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


@pytest.mark.parametrize("store_id", [501, 502, 503])
def test_synthetic_company_store_sales_location_matrix_is_explicit(store_id: int) -> None:
    document = _synthetic_mapping()
    row = document["stores"][str(store_id)]

    target = resolve_p1_erp_target(
        store_id=store_id,
        local_company_id=row["local_company_id"],
        mappings_json=json.dumps(document),
        fallback_target_company_id=9991,
        fallback_sales_location_id=9992,
        unit_id=row["unit_id"],
        tenant_id=row["tenant_id"],
        legal_entity_id=row["legal_entity_id"],
    )

    assert target is not None
    assert target.local_store_id == store_id
    assert target.local_company_id == row["local_company_id"]
    assert target.target_company_id == row["target_company_id"]
    assert target.sales_location_id == row["sales_location_id"]
    assert target.sales_location_id != target.local_store_id
    assert target.mapping_status == "SYNTHETIC_ONLY"


def test_synthetic_store_rejects_cross_company_context() -> None:
    document = _synthetic_mapping()
    row = document["stores"]["501"]

    with pytest.raises(P1ErpTargetMappingError, match="erp_target_mapping_company_mismatch"):
        resolve_p1_erp_target(
            store_id=501,
            local_company_id=1599,
            mappings_json=json.dumps(document),
            fallback_target_company_id=9991,
            fallback_sales_location_id=9992,
            unit_id=row["unit_id"],
            tenant_id=row["tenant_id"],
            legal_entity_id=row["legal_entity_id"],
        )


def test_identity_mapping_requires_explicit_company_scope() -> None:
    mapping = json.dumps(
        {
            "stores": {
                "601": {
                    "unit_id": "synthetic-wj-unit-missing-company-001",
                    "tenant_id": "synthetic-wj-tenant-global-001",
                    "legal_entity_id": "synthetic-wj-legal-entity-missing-company-001",
                    "target_company_id": 2601,
                    "sales_location_id": 9601,
                }
            }
        }
    )

    with pytest.raises(P1ErpTargetMappingError, match="erp_target_mapping_company_missing"):
        parse_p1_erp_target_mappings(mapping)


def test_duplicate_json_mapping_key_fails_closed() -> None:
    mapping = (
        '{"stores":{"701":{"local_company_id":1701,'
        '"target_company_id":2701,"sales_location_id":9701},'
        '"701":{"local_company_id":1701,'
        '"target_company_id":2701,"sales_location_id":9701}}}'
    )

    with pytest.raises(P1ErpTargetMappingError, match="erp_target_mapping_duplicate_key"):
        parse_p1_erp_target_mappings(mapping)
