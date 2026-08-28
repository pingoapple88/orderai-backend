# T5 付款方式自助管理：受控交接

**狀態：`BLOCKED`（正式管理能力）／`PASS`（`DEMO_MOCK` contract 與 fixture）。** 使用者要求的付款方式新增、切換、修改設定與移除，必須在 provider-neutral 的持久化／vault abstraction、中央 owner 授權與已核准 migration 完整存在後，才可對外提供 API。

目前 `IPaymentProvider` 僅有 `create_payment` 與 `get_status`，既有 `BillingRecord.payment_method` 只保存既有帳務記錄的支付方式文字，並不是可安全管理的付款方式 vault。現有 `plans`、`billing_records` 與 Alembic chain 中沒有 payment method profile、default selection、token reference 或設定版本的核准資料模型。因此 T5 未以 client payload、`BillingRecord` 或 process-local data 假裝可持久化付款方式。

| 使用者期待操作 | T5 synthetic screen 狀態 | 正式實作前置條件 |
|---|---|---|
| 新增付款方式 | `owner_gate` | [TODO: 待人工確認] payment method vault owner、tokenization boundary、callback authority。 |
| 切換預設方式 | `owner_gate` | [TODO: 待人工確認] provider capability 與 subscription billing selection contract。 |
| 修改設定 | `owner_gate` | [TODO: 待人工確認] 可修改設定白名單、PII／PCI 資料責任與 audit payload contract。 |
| 移除方式 | `blocked`／`owner_gate` | 最後一個 active method 必須 `blocked`；其他刪除仍需 lifecycle、reconciliation 與 retention policy。 |
| 未知 provider 或狀態 | `manual_review` | 不建立支付、不調整 entitlement、不自動重試。 |

## T1 handoff

T1 可用 `orderai.payment_method_management` 顯示五個 synthetic status，而非真實付款頁。所有 CTA 在 owner Gate 未解除前必須顯示 `owner_gate`、`blocked` 或 `manual_review`，不可蒐集卡號、銀行帳號、token、provider reference、company／store／user identifier 或其他付款資料。

| Asset | 路徑 |
|---|---|
| screen contract | `src/ui/contracts/orderai/orderai.payment_method_management.json` |
| synthetic fixture | `src/ui/fixtures/orderai/orderai_payment_method_management.json` |
| focused harness | `tests/ui/orderai/test_payment_method_management_contract.py` |

## 中央 Gate

1. [TODO: 待人工確認] payment method vault／tokenization owner 與資料保留／刪除政策。
2. [TODO: 待人工確認] `IPaymentProvider` 的付款方式 provider-neutral extension、callback authority 與 error／reconciliation contract。
3. [TODO: 待人工確認] payment method profile／default selection 的 migration、tenant constraints、idempotency key 與 audit schema。
4. [TODO: 待人工確認] sandbox test environment、PCI／PII boundary 與核准測試資料。
