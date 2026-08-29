# T5 OrderAI Evidence Index

| Scope | Source commit | Evidence | Result |
|---|---|---|---|
| Canonical T1 read-only module input | `f8d5ef934087e4e26f3c7c641d9caf6a1b400fca` | `evidence/t5_canonical_module_input_smoke.txt` | 17 passed; compile／diff／scans exit 0. |
| Parse／risk review／Queue | `07584532a4206a656e7940efc81c0003ef748563` | `evidence/t5_round1_parse_risk_queue_smoke.txt` | Synthetic fallback 11 passed; existing database-dependent suite RETURN_FOR_EVIDENCE. |
| Smart agriculture synthetic presentation | `8df9f2a2af8cddd1c357ab3d767db94a3d0504a3` | `evidence/t5_smart_agri_expo_smoke.txt` | 10 passed. |
| Self-service restart coverage | `ec9d0ed0a59079ff48d1fb0d7c74ba7ad63eb398` | `evidence/t5_orderai_restart_coverage_smoke_2026-08-29.txt` | 8 passed. |
| Day 31–90 read models／readiness | `1df46be561613642b61329652359e0bacce75252` | `evidence/t5_day31_90_readmodels_smoke.txt` | 13 passed. |
| Payment-method synthetic lifecycle | `79f33bd6c19f1380d48ec66560e2a3e6bf69117a` | `evidence/t5_payment_method_lifecycle_w2_02_smoke.txt` | 6 passed. |

All entries are local-only／synthetic evidence unless explicitly stated otherwise. No entry authorizes formal provider connection, customer PII access, production data, payment processing, tax handling, OAuth merge, or database write.
