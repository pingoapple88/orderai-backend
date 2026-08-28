# T5 Day 31–90 增量驗收更新

## Day 31–60：已完成的 local-only read model

| 交付 | 狀態 | 實作邊界 |
|---|---|---|
| 帳務歷史 | PASS | `/api/v1/orderai/subscriptions/billing-history` 僅以 server-derived principal 篩選 user／store，且只回傳 integer minor units、currency、status 與 UTC timestamp。 |
| AI 額度用量 | PASS | `/api/v1/orderai/subscriptions/usage` 僅統計目前 UTC 月份的既有 `AIUsageLog`；非 active entitlement、非整數額度或異常資料一律 `manual_review`。 |
| 發票歷史 | PASS | `/api/v1/orderai/subscriptions/invoices` 只回傳 principal scoped 最小 invoice status，不含 internal ID 或 provider reference。 |
| payment query | PASS | `/status` 的 payment status 僅取既有帳務記錄的白名單狀態；未知值映射 `manual_review`。 |
| 客服／錯誤狀態 | PASS | 透過最小 status payload 回傳 `manual_review`、`blocked`、`inactive`、`past_due` 等既有 lifecycle 結果，不新增客服 connector。 |
| 獨立產品設定 | RETURN_FOR_EVIDENCE | 設定程式已外部化 provider name 與訂閱週期；`.env.example` names-only 補充仍須經受控設定流程納入 Git。 |

## Day 61–90：受控準備

| 範圍 | 狀態 | 結果 |
|---|---|---|
| sandbox provider readiness | PASS | 僅以 local mock 投影 `ready_for_synthetic_test`；未宣稱或連接正式 sandbox。 |
| usage／cost projection | PASS | 使用既有 usage read model；未知成本不提供數值，一律 `manual_review`。 |
| backup／recovery | RETURN_FOR_EVIDENCE | contract 明確 `owner_gate`／`no_production_data`，未執行 backup 或 restore。 |
| EventBus mapping | PASS | 只映射現有 `order.created`、`order.updated`、`order.confirmed`；subscription events 為空，未新增事件。 |

## 測試與交接

| 項目 | 結果 | Evidence |
|---|---|---|
| affected smoke | PASS：13 passed，exit 0 | `evidence/t5_day31_90_readmodels_smoke.txt` |
| compile／diff | PASS：均 exit 0 | `evidence/t5_day31_90_readmodels_smoke.txt` |
| scan | PASS：external／secret、shadow／analytics、unapproved event 均 MATCH=NO | `evidence/t5_day31_90_readmodels_smoke.txt` |
| T1 handoff | OPEN | T1 需以 pinned source commit 掛載 `orderai.subscription_lifecycle`、`orderai.operations_readiness` 與既有 parse／risk／Queue screens。 |
| central Gate | BLOCKED | 正式 provider sandbox、callback authority、invoice／tax policy、backup／recovery 演練及 EventBus 白名單均待 owner 確認。 |
