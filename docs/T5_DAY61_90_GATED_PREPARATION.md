# T5 Day 61–90 受控準備與交接

**狀態：`RETURN_FOR_EVIDENCE`。** 本文件只描述可在 T5 feature branch 以 local-only asset 驗證的準備成果，不表示正式 sandbox connector、成本帳務、備份／恢復或事件傳輸已啟用。

| 範圍 | T5 已完成的準備 | 目前界線 | 交接項 |
|---|---|---|---|
| sandbox provider | 既有 `LocalSubscriptionProvider` 與 `LocalManualReviewInvoiceProvider` 的 local mock contract 已由 Day 1–30 測試覆蓋。 | 不含正式 endpoint、key、callback 或第三方 sandbox。 | 中央 owner 確認 provider-neutral sandbox 後，才可新增實作。 |
| usage／cost | `AIUsageLog` 既有模型與 principal-scoped `/usage` read model 可提供用量；未知成本固定為 `manual_review`。 | 不新增成本資料表、不估算或呈現金額。 | 中央確認成本資料定義與 retention policy。 |
| backup／recovery | screen contract／fixture 明確標示 `owner_gate` 與 `no_production_data`。 | 不執行 backup、restore 或 production data 存取。 | 基礎設施 owner 提供已核准的演練環境與 RPO／RTO 標準。 |
| EventBus | 只映射既有 `order.created`、`order.updated`、`order.confirmed`。 | `subscriptionEvents` 為空；不新增第五事件、outbox、transport 或跨模組 publish。 | 中央確認事件清單與 payload contract 後才可實作。 |

## T1 handoff

T1 可在 Demo AppShell 以 `orderai.operations_readiness` 呈現兩個合成狀態：`local_sandbox_provider_ready` 與 `unknown_provider_fails_closed`。未知 provider、未知成本與 recovery request 都必須顯示 `manual_review` 或 `owner_gate`，不可顯示為已啟用或已完成。

| Asset | 路徑 |
|---|---|
| screen contract | `src/ui/contracts/orderai/orderai.operations_readiness.json` |
| synthetic fixture | `src/ui/fixtures/orderai/orderai_operations_readiness.json` |
| focused harness | `tests/ui/orderai/test_operations_readiness_contract.py` |

## Open Gate

1. [TODO: 待人工確認] payment／subscription／invoice sandbox owner、callback authority、費率與資料保留政策。
2. [TODO: 待人工確認] backup／restore 演練環境、RPO／RTO 與核准程序。
3. [TODO: 待人工確認] EventBus 可發布事件的中央白名單與跨模組 payload contract。
