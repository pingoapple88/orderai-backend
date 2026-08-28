# OrderAI 自助訂閱展示交接

> **Screen contract**：`ORDERAI-SUBSCRIPTION-W2-01`。所有資料均為 `DEMO_MOCK`；不得將 fixture 連接至正式 Provider、資料庫、LINE、LLM、支付或發票服務。

T1 可將 `src/ui/fixtures/orderai/orderai_subscription_lifecycle.json` 掛載至 `orderai.subscription_lifecycle`，並以五個情境呈現產品入口、direct／dealer／enterprise 通路、付款狀態、entitlement、訂閱管理與發票狀態。畫面不得顯示 company、store、user、Provider reference 或其他內部識別值。

| 情境 | 顯示結果 | 可操作控制 |
|---|---|---|
| `direct-pending-payment` | entitlement 等待啟用 | cancel |
| `dealer-active-entitlement` | entitlement active；發票 manual review | renew、change plan、cancel、request invoice |
| `enterprise-provider-timeout` | manual review／blocked | 無；不得自動啟用或重試 |
| `direct-past-due` | entitlement blocked | renew、cancel |
| `dealer-canceled` | subscription canceled | 無；duplicate idempotency 應明確顯示 blocked |

> 已提供資料不包含金額。若 T1 未來需要顯示金額，只能讀取 server-generated integer minor units，並標示通路、版本日期及「以官網最新價格為準」。
