# Wanjiaxiang P1 Target Mapping

## Scope

This slice adds a provider-neutral, configuration-only mapping from a local
OrderAI `store_id` and `company_id` to an ERP `target_company_id` and
`sales_location_id`, with optional Wanjiaxiang `unit_id`, `tenant_id`, and
`legal_entity_id` identity binding. It does not select a vendor, call an ERP,
add a migration, or bypass human review.

## Synthetic configuration

```json
{
  "stores": {
    "101": {
      "unit_id": "synthetic-wj-unit-direct-001",
      "tenant_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      "legal_entity_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      "local_company_id": 11,
      "target_company_id": 201,
      "sales_location_id": 101,
      "mapping_status": "SYNTHETIC_ONLY"
    },
    "102": {
      "local_company_id": 12,
      "target_company_id": 202,
      "sales_location_id": 102
    }
  }
}
```

The mapping is externalized through `P1_ERP_TARGET_MAPPINGS_JSON`. If the JSON
is non-empty, a missing store or local-company mismatch fails closed. If the
caller provides Wanjiaxiang unit／tenant／legal-entity context, all three
identity fields must match and an empty mapping cannot use the legacy fallback.
Without that optional WJ context, the existing single-target
`P1_ERP_TARGET_COMPANY_ID` and `P1_ERP_SALES_LOCATION_ID` fallback remains
available for backward-compatible controlled deployments.

## WJ boundary

- The numeric values above are synthetic only.
- `store_id` is not treated as `sales_location_id` without an explicit mapping.
- Product mapping remains separately externalized through
  `P1_ERP_PRODUCT_ID_MAP_JSON`.
- `mapping_status` is descriptive only; `SYNTHETIC_ONLY` does not authorize a
  formal ERP write.
- Human review, customer confirmation, audit, PII protection, idempotency and
  blocked ERP delivery remain unchanged.
- Formal company／legal-entity／ERP mapping and provider credentials remain
  owner-gated.

## Synthetic hardening matrix

`tests/fixtures/wanjiaxiang_p1_mapping_synthetic_v1.json` contains three
synthetic rows representing headquarters, dealer and store scopes. Each row
binds a local company, store, unit, tenant, legal entity, target company and
sales location. The test deliberately uses different numeric values for
`store_id` and `sales_location_id`; the latter is never inferred from the
former.

The parser stops before resolution when it finds:

- duplicate JSON object keys: `erp_target_mapping_duplicate_key`;
- identity fields without an explicit `local_company_id`:
  `erp_target_mapping_company_missing`;
- a caller company that differs from the mapped local company:
  `erp_target_mapping_company_mismatch`;
- missing store, unit, tenant or legal-entity scope, using the existing
  fail-closed reason codes.
