"""Provider-neutral P1 ERP target mapping with explicit store/company scope.

The mapping is configuration-only. It does not connect to an ERP, choose a
provider, or create a database record. Missing, malformed, or mismatched
mapping fails closed so a local OrderAI company is never guessed to be an ERP
company.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class P1ErpTarget:
    """One local Store to external ERP company/sales-location mapping."""

    local_store_id: int
    local_company_id: int | None
    target_company_id: int
    sales_location_id: int
    unit_id: str | None = None
    tenant_id: str | None = None
    legal_entity_id: str | None = None
    mapping_status: str = "CONFIGURED"


class P1ErpTargetMappingError(ValueError):
    """Configuration or scope mismatch that must stop P1 ERP preparation."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class _DuplicateMappingKey(ValueError):
    """Internal parser signal for duplicate JSON object keys."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateMappingKey(key)
        result[key] = value
    return result


def _positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise P1ErpTargetMappingError("erp_target_mapping_invalid")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise P1ErpTargetMappingError("erp_target_mapping_invalid") from exc
    if number <= 0:
        raise P1ErpTargetMappingError("erp_target_mapping_invalid")
    return number


def parse_p1_erp_target_mappings(raw_json: str) -> dict[int, P1ErpTarget]:
    """Parse the externalized store-scoped mapping without guessing defaults."""
    if not raw_json.strip() or raw_json.strip() == "{}":
        return {}
    try:
        document = json.loads(raw_json, object_pairs_hook=_reject_duplicate_keys)
    except _DuplicateMappingKey as exc:
        raise P1ErpTargetMappingError("erp_target_mapping_duplicate_key") from exc
    except json.JSONDecodeError as exc:
        raise P1ErpTargetMappingError("erp_target_mapping_invalid") from exc
    if not isinstance(document, dict) or not isinstance(document.get("stores"), dict):
        raise P1ErpTargetMappingError("erp_target_mapping_invalid")

    result: dict[int, P1ErpTarget] = {}
    for raw_store_id, raw_target in document["stores"].items():
        store_id = _positive_int(raw_store_id, field="store_id")
        if not isinstance(raw_target, dict):
            raise P1ErpTargetMappingError("erp_target_mapping_invalid")
        raw_unit_id = raw_target.get("unit_id")
        raw_tenant_id = raw_target.get("tenant_id")
        raw_legal_entity_id = raw_target.get("legal_entity_id")
        for value in (raw_unit_id, raw_tenant_id, raw_legal_entity_id):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise P1ErpTargetMappingError("erp_target_mapping_invalid")
        raw_local_company = raw_target.get("local_company_id")
        local_company_id = (
            None
            if raw_local_company is None
            else _positive_int(raw_local_company, field="local_company_id")
        )
        if (
            any(value is not None for value in (raw_unit_id, raw_tenant_id, raw_legal_entity_id))
            and local_company_id is None
        ):
            raise P1ErpTargetMappingError("erp_target_mapping_company_missing")
        result[store_id] = P1ErpTarget(
            local_store_id=store_id,
            local_company_id=local_company_id,
                target_company_id=_positive_int(
                    raw_target.get("target_company_id"), field="target_company_id"
                ),
                sales_location_id=_positive_int(
                    raw_target.get("sales_location_id"), field="sales_location_id"
                ),
                unit_id=raw_unit_id,
                tenant_id=raw_tenant_id,
                legal_entity_id=raw_legal_entity_id,
                mapping_status=str(raw_target.get("mapping_status") or "CONFIGURED"),
            )
    return result


def resolve_p1_erp_target(
    *,
    store_id: int,
    local_company_id: int | None,
    mappings_json: str,
    fallback_target_company_id: int,
    fallback_sales_location_id: int,
    unit_id: str | None = None,
    tenant_id: str | None = None,
    legal_entity_id: str | None = None,
) -> P1ErpTarget | None:
    """Resolve a target using store scope, with legacy fallback only when unmapped."""
    mappings = parse_p1_erp_target_mappings(mappings_json)
    if mappings:
        target = mappings.get(store_id)
        if target is None:
            raise P1ErpTargetMappingError("erp_target_mapping_missing")
        if target.local_company_id is not None and target.local_company_id != local_company_id:
            raise P1ErpTargetMappingError("erp_target_mapping_company_mismatch")
        if unit_id is not None and target.unit_id != unit_id:
            raise P1ErpTargetMappingError("erp_target_mapping_unit_mismatch")
        if tenant_id is not None and target.tenant_id != tenant_id:
            raise P1ErpTargetMappingError("erp_target_mapping_tenant_mismatch")
        if legal_entity_id is not None and target.legal_entity_id != legal_entity_id:
            raise P1ErpTargetMappingError("erp_target_mapping_legal_entity_mismatch")
        return target

    if fallback_target_company_id <= 0 or fallback_sales_location_id <= 0:
        return None
    if unit_id is not None or tenant_id is not None or legal_entity_id is not None:
        raise P1ErpTargetMappingError("erp_target_mapping_identity_missing")
    return P1ErpTarget(
        local_store_id=store_id,
        local_company_id=local_company_id,
        target_company_id=fallback_target_company_id,
        sales_location_id=fallback_sales_location_id,
    )


__all__ = [
    "P1ErpTarget",
    "P1ErpTargetMappingError",
    "parse_p1_erp_target_mappings",
    "resolve_p1_erp_target",
]
