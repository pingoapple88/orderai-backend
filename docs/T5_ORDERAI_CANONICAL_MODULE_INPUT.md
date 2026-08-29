# T5 OrderAI Canonical Module Input for T1

## Read-only integration use

此文件與 `src/ui/contracts/orderai/orderai.canonical_module_input.json` 是 T1 唯一可讀取的 OrderAI canonical input。T1 必須固定至 JSON 所列 `sourceCommit`，只使用同一 SHA 所含的 `DEMO_MOCK` fixture；**不得在 Demo 中 live fetch、不得傳送 JWT、不得把 customer／company／store 資料寫回 OrderAI**。

## Canonical identity

| Field | Value |
|---|---|
| module_id | `orderai` |
| repository | `pingoapple88/orderai-backend` |
| branch | `feat/orderai-self-service-subscriptions` |
| source_commit | `07584532a4206a656e7940efc81c0003ef748563` |
| parent／rollback | `8df9f2a2af8cddd1c357ab3d767db94a3d0504a3` |
| hardening lineage | `99279894d347f2dd2d19a07735d7e937e0547f39` |
| owner | T5 |
| mode／availability／evidence_level | `DEMO_MOCK`／`available_synthetic`／`SYNTHETIC_CONTRACT_AND_FOCUSED_SMOKE` |

## Read-only route contract

| Route | Method | Required input | Safe output | Error／blocked／return |
|---|---|---|---|---|
| `/api/v1/module/orderai/health` | GET | None | `status`、`module_key`、`module_version` | Unavailable HTTP behavior `[TODO: 待人工確認]`；T1 return route `[TODO: 待 T1 pinned manifest 指定]`。 |
| `/api/v1/module/orderai/manifest` | GET | None | module／locale／capability metadata | Unavailable HTTP behavior `[TODO: 待人工確認]`；同上。 |
| `/api/v1/module/orderai/plans` | GET | Optional `channel=direct|dealer|enterprise`；default `direct` | plan name、channel、integer minor-unit price、currency、AI limit、price version／disclaimer | Invalid channel HTTP behavior `[TODO: 待人工確認]`；無方案為 `empty`。 |
| `/api/v1/module/orderai/status` | GET | `Authorization: Bearer <JWT>` | plan／channel／AI usage／limit／status | Missing、invalid、expired、malformed bearer token 為 HTTP 401／`blocked`。 |
| `/api/v1/orderai/subscriptions/status` | GET | `Authorization: Bearer <JWT>` | subscription／entitlement／payment／invoice status、quota、UTC period end | Missing bearer 為 401／`blocked`；unknown payment、invoice、entitlement 為 `manual_review`。 |
| `/api/v1/orderai/subscriptions/billing-history` | GET | `Authorization: Bearer <JWT>` | amount minor、currency、status、UTC created time | 401／`blocked`；unknown status `manual_review`；無資料 `empty`。 |
| `/api/v1/orderai/subscriptions/usage` | GET | `Authorization: Bearer <JWT>` | used／limit／remaining／status／UTC cycle start | 401／`blocked`；quota／entitlement不明 `manual_review`。 |
| `/api/v1/orderai/subscriptions/invoices`／`latest` | GET | `Authorization: Bearer <JWT>` | invoice status、amount minor、currency、UTC issued／due time | 401／`blocked`；invoice未知 `manual_review`；無資料 `empty`。 |

> T1 的 Modular Demo 僅以 fixture 模擬本表，**不可**在 browser 呼叫上述 endpoint。所有 server scope 都由 JWT principal 決定，client 不得傳送或宣稱 `companyId`、`storeId`、`userId` authority。

## Fixture catalog

| screen_id | fixture_path | availability | 可展示範圍 |
|---|---|---|---|
| `orderai.integration_entry` | `src/ui/fixtures/orderai/orderai_integration_entry.json` | `available_synthetic` | OrderAI self-service總入口。 |
| `orderai.subscription_lifecycle` | `src/ui/fixtures/orderai/orderai_subscription_lifecycle.json` | `available_synthetic` | 三通路、subscription、usage、billing、invoice status。 |
| `orderai.payment_method_management` | `src/ui/fixtures/orderai/orderai_payment_method_management.json` | `owner_gate` | 只能顯示合成安全摘要與Gate，不可存取 payment token。 |
| `orderai.parse_result` | `src/ui/fixtures/orderai/orderai_parse_result.json` | `available_synthetic` | 0.85 approval、低信心、unmatched、PII redaction、blocked。 |
| `orderai.risk_review` | `src/ui/fixtures/orderai/orderai_risk_review.json` | `available_synthetic` | approved／needs_review、reason code、hash-only audit reference。 |
| `orderai.queue` | `src/ui/fixtures/orderai/orderai_queue.json` | `available_synthetic` | loading／empty、dedupe、limited retry、dead letter、blocked。 |
| `orderai.smart_agri_expo` | `src/ui/fixtures/orderai/orderai_smart_agri_expo.json` | `available_synthetic` | 智慧農業展全合成 customer／AI／promotion presentation。 |

## Evidence index

| Evidence path | Purpose | Actual result |
|---|---|---|
| `evidence/t5_round1_parse_risk_queue_smoke.txt` | parse／risk／queue screen assets | synthetic fallback `11 passed`，exit 0；compile／diff／scans exit 0。 |
| `evidence/t5_smart_agri_expo_smoke.txt` | smart agriculture demo | `10 passed`，exit 0。 |
| `evidence/t5_orderai_restart_coverage_smoke_2026-08-29.txt` | self-service coverage reset | `8 passed`，exit 0。 |
| `evidence/t5_day31_90_readmodels_smoke.txt` | billing／usage／invoice read models | `13 passed`，exit 0。 |
| `evidence/t5_payment_method_lifecycle_w2_02_smoke.txt` | payment-method synthetic lifecycle | `6 passed`，exit 0。 |

## Explicitly blocked or planned

正式 OAuth、資料庫寫入／runtime、payment／payment-method vault、invoice credential／tax、formal provider sandbox均為 `BLOCKED`，owner如 machine-readable input 所列。T1 visual route mount、RWD、keyboard、ARIA-live、reduced-motion與customer journey evidence為 `PLANNED`，待 T1 pinned manifest 指定 route後完成。

## T1 next action

以 `07584532a4206a656e7940efc81c0003ef748563` 為唯一 source，載入 JSON fixture，建立單一 Demo route manifest；若任一 fixture／contract缺失或 SHA 不一致，維持 `blocked` fallback並回填 `XREQ-T5-0007`。不要自行補 API、provider、OAuth、billing、payment或invoice core。
