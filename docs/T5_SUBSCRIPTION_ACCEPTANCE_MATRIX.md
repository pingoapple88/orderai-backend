# T5 OrderAI Self-service Subscription Lifecycle — Acceptance Matrix

> **Scope**：本文件僅驗收自 `99279894d347f2dd2d19a07735d7e937e0547f39` 增量的 T5 subscription、entitlement、invoice status 與 T1 `DEMO_MOCK` 展示接點。未接正式 payment、invoice、LINE、LLM、Redis 或正式資料。所有時間資料採 UTC；金額只使用 integer minor units。

| 欄位 | 證據／結果 |
|---|---|
| Repository | `pingoapple88/orderai-backend` |
| Feature branch | `feat/orderai-self-service-subscriptions` |
| Base SHA | `99279894d347f2dd2d19a07735d7e937e0547f39` |
| 最新 source SHA | `e00492156e313363d0885c58fd610f7b8065e59d` |
| Source rollback | `0786f94c8c671bbe74816d1154b9d512b71745c9`；完整回退至 W2 基線為 `99279894d347f2dd2d19a07735d7e937e0547f39` |
| 最小 smoke | `evidence/t5_subscription_acceptance_smoke.txt` |

## 1. 實際 changed paths

| 類型 | Paths |
|---|---|
| Interface／Provider | `app/core/interfaces/subscription_provider.py`、`app/core/interfaces/invoice_provider.py`、`app/providers/local_subscription.py`、`app/providers/__init__.py` |
| Lifecycle／API | `app/services/subscription_service.py`、`app/api/v1/subscriptions.py`、`app/schemas/__init__.py`、`app/main.py` |
| Persistence | `app/models/__init__.py`、`alembic/versions/w2_orderai_subscriptions.py`、`tests/conftest.py` |
| T1 展示接點 | `src/ui/contracts/orderai/orderai.subscription_lifecycle.json`、`src/ui/fixtures/orderai/orderai_subscription_lifecycle.json`、`docs/ORDERAI_SUBSCRIPTION_T1_HANDOFF.md` |
| Tests／evidence | `tests/test_subscription_service.py`、`tests/test_subscription_api.py`、`tests/ui/orderai/test_subscription_lifecycle_contract.py`、`evidence/t5_subscription_acceptance_smoke.txt`、本文件 |

## 2. 既有資產 reuse matrix

| Repository／branch | 檔案 | reuse_mode | 實際使用方式 |
|---|---|---|---|
| `pingoapple88/orderai-backend@99279894…` | `app/models.Plan`、`BillingRecord`、`AuditLog` | `REUSE_AS_IS` | 沿用方案 channel、integer minor unit、帳務記錄與稽核模型。 |
| 同上 | `app/services/module_service.py`、`app/api/v1/module.py` | `REUSE_AS_IS` | 沿用 company-scoped idempotency、pending activation 與 principal scope 邊界。 |
| 同上 | `app/core/interfaces/payment_provider.py`、既有 StallPay adapter | `INTEGRATE_VIA_ADAPTER` | 訂閱 service 僅依 `IPaymentProvider` 呼叫；測試僅注入 mock。 |
| 同上 | parse、risk、review、Queue、dead-letter contracts | `REUSE_AS_IS` | 無修改；產品入口只以 T1 handoff contract 說明連接點。 |
| 同上 | `app/services/pii_redaction.py` | `REUSE_AS_IS` | 訂閱 audit 僅存 status、channel、reason control fields；不送原始付款資料或 PII。 |
| 正式付款／發票 connector | [TODO: 待人工確認] | `NEEDS_OWNER_DECISION` | 本輪僅 local mock／manual-review provider；不得以 placeholder 宣稱正式連接。 |

## 3. 新增 route、screen、Adapter、fixture、harness

| 類別 | 交付 | 結果 |
|---|---|---|
| Route | `/api/v1/orderai/subscriptions/intents`、`/status`、`/actions`、`/invoices`、`/invoices/latest` | PASS：route scope 由 `get_current_principal` 推導；請求 schema 禁止 client company／store／user scope 欄位。 |
| Interface | `ISubscriptionProvider`、`IInvoiceProvider` | PASS：未知 transition／invoice status 均轉 manual review。 |
| Adapter | `LocalSubscriptionProvider`、`LocalManualReviewInvoiceProvider` | PASS：只提供 deterministic／manual-review synthetic 行為。 |
| Screen | `orderai.subscription_lifecycle`，`ORDERAI-SUBSCRIPTION-W2-01` | PASS：定義 product entry、channel、payment、entitlement、subscription 與 invoice view。 |
| Fixture | `src/ui/fixtures/orderai/orderai_subscription_lifecycle.json` | PASS：direct／dealer／enterprise、pending、active、timeout、past_due、canceled 的 `DEMO_MOCK` 情境。 |
| Harness | `tests/test_subscription_service.py`、`tests/test_subscription_api.py`、`tests/ui/orderai/test_subscription_lifecycle_contract.py` | PASS：23 passed 的最小 affected smoke。 |

## 4. 方案與 lifecycle Acceptance Criteria

| 項目 | 結果 | 證據 |
|---|---|---|
| 既有方案與 direct／dealer／enterprise channel | PASS | `tests/test_subscription_service.py::test_all_channels_require_their_own_existing_plan` |
| customer subscription intent | PASS | `tests/test_subscription_service.py::test_intent_is_company_scoped_idempotent_and_pending_without_payment` |
| payment pending／paid／failed／unknown | PASS | `tests/test_subscription_service.py::test_paid_adapter_can_activate_entitlement_but_unknown_or_failure_is_manual_review`；未知為 `manual_review`。 |
| Provider error／timeout | PASS | `tests/test_subscription_service.py::test_provider_failure_never_auto_activates_and_invoice_stays_manual_review`；理由碼僅為控制欄位。 |
| entitlement activation | PASS | 僅 `paid` 且 transition 為 `active` 時設為 `active`，並寫入 UTC period end。 |
| subscription renew／change／cancel／past_due | PASS | `tests/test_subscription_service.py::test_renew_change_cancel_and_cross_company_access_follow_fail_closed_rules`、`test_trusted_payment_reconciliation_supports_overdue_but_unknown_is_manual_review`。 |
| invoice status／duplicate prevention | PASS | local invoice 一律 `manual_review`；相同 company-scoped idempotency key 回傳既有 invoice。 |
| 正式 payment／invoice processing | NOT_APPLICABLE | 本輪禁止；由 owner 選定可替換 connector 後另行驗證。 |

## 5. 安全與資料治理 Acceptance Criteria

| 項目 | 結果 | 證據 |
|---|---|---|
| Tenant scope／RBAC | PASS | 新 route 第一層 `get_current_principal`；API test 拒絕 client `companyId`。 |
| PII | PASS | audit 的 `new_value` 不含 provider／payment reference 或 raw PII；見 `test_provider_failure_never_auto_activates_and_invoice_stays_manual_review`。 |
| UTC | PASS | `current_period_end` 與 `canceled_at` 測試驗證 timezone-aware UTC。 |
| Minor units | PASS | Plan、BillingRecord、InvoiceRecord 僅使用 `int` amount／amount_minor，測試拒絕非整數 plan amount。 |
| Idempotency | PASS | subscription 與 invoice key 均以 `company_id` namespace SHA-256 儲存；重送不重複寫入。 |
| Audit | PASS | intent、action、payment reconciliation、invoice request 均紀錄控制欄位；無 raw provider payload。 |
| OAuth isolation | PASS | 本輪 changed paths 不含 Auth route／OAuth test；完整 pytest 的既有 Auth blocker 未重跑。 |

## 6. Locale、RWD 與掃描

| 項目 | 結果 | 證據 |
|---|---|---|
| 五語系 contract | PASS | fixture 覆蓋 `zh-Hant-TW`、`en-US`、`th-TH`、`ja-JP`、`id-ID`；`test_subscription_lifecycle_contract.py`。 |
| T1 desktop／mobile 實際畫面 | RETURN_FOR_EVIDENCE | [TODO: 待 T1 依 handoff 掛載後，提供 1440×900／390×844、keyboard、ARIA live、reduced-motion 與無水平溢出 evidence]。 |
| External／secret／shadow scan | PASS | `evidence/t5_subscription_acceptance_smoke.txt`：`MATCH=NO`。 |

## 7. Open TODO、central hard Gate 與 next action

| 類型 | 項目 |
|---|---|
| Open TODO | `.env.example` 已在本機補上 `SUBSCRIPTION_PROVIDER`、`INVOICE_PROVIDER`、`SUBSCRIPTION_PERIOD_DAYS`，但尚未成為受控 Git 交付；[TODO: 待人工確認] 以核准設定流程納入 source control。 |
| Cross-team request | T1 以 pinned source commit 掛載 `orderai.subscription_lifecycle` fixture／contract，並提供 RWD、ARIA、keyboard、reduced-motion evidence。 |
| Central hard Gate | OAuth baseline 的完整 suite、正式 payment／invoice provider 選定、實際 connector contract、staging migration／backup／rollback drill 均不在本輪驗收範圍。 |
| Next action | 完成 evidence commit 並推送 feature branch；其後以 final HEAD 回填共享看板與 Manifest 的 T5 row。 |
