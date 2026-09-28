# Wanjiaxiang P1 Target Mapping

## Scope

This slice adds a provider-neutral, configuration-only mapping from a local
OrderAI `store_id` and `company_id` to an ERP `target_company_id` and
`sales_location_id`. It does not select a vendor, call an ERP, add a migration,
or bypass human review.

## Synthetic configuration

```json
{
  "stores": {
    "101": {
      "local_company_id": 11,
      "target_company_id": 201,
      "sales_location_id": 101
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
is non-empty, a missing store or local-company mismatch fails closed. If it is
empty, the existing single-target `P1_ERP_TARGET_COMPANY_ID` and
`P1_ERP_SALES_LOCATION_ID` fallback remains available for backward-compatible
controlled deployments.

## WJ boundary

- The numeric values above are synthetic only.
- `store_id` is not treated as `sales_location_id` without an explicit mapping.
- Product mapping remains separately externalized through
  `P1_ERP_PRODUCT_ID_MAP_JSON`.
- Human review, customer confirmation, audit, PII protection, idempotency and
  blocked ERP delivery remain unchanged.
- Formal company／legal-entity／ERP mapping and provider credentials remain
  owner-gated.
