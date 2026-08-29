# T5 OrderAI 唯一 integration baseline

本文件定義 T1 掛載 OrderAI synthetic presentation 的唯一來源：`feat/orderai-self-service-subscriptions` 的 **final pinned HEAD**。T1 必須從共享整合 Manifest 的 T5 row 取得該次推送的完整 SHA；不得混用不同 branch、未推送工作樹、OAuth 修正 branch 或 StallPay-V2 payment／invoice core。

| 範圍 | 來源 asset | reuse_mode | T1 呈現界線 |
|---|---|---|---|
| 獨立銷售入口、三通路、訂閱、entitlement、帳務、發票 | `orderai.subscription_lifecycle`／`ORDERAI-SUBSCRIPTION-W2-01` | `REUSE_AS_IS` | 僅 `DEMO_MOCK`；未知付款／發票為 `manual_review`。 |
| AI 額度、帳務 history、invoice history、sandbox／cost／backup／EventBus readiness | `orderai.operations_readiness`／`ORDERAI-OPERATIONS-W2-01` | `REUSE_AS_IS` | 僅 local mock／mapping-only；backup 為 `owner_gate`。 |
| 付款方式管理 | `orderai.payment_method_management`／`ORDERAI-PAYMENT-METHOD-W2-01` | `INTEGRATE_VIA_ADAPTER` | 新增、切換、修改、移除均為 `owner_gate`；不可收集 payment token、卡號或帳戶資料。 |
| parse、risk、review、Queue／dead-letter | `orderai.integration_entry`／`ORDERAI-INTEGRATION-W2-01` | `REUSE_AS_IS` | 只呈現既有 `needs_review`、`provider_timeout`、`dead_letter` fail-closed state。 |

## T1 input

T1 的入口為 `orderai.integration_entry`，fixture 為 `src/ui/fixtures/orderai/orderai_integration_entry.json`。它以五個 locale 對應 direct、dealer、enterprise 與 parse／risk／Queue 狀態，且不包含真實使用者、公司、店家、付款、發票、卡號、帳戶、token、provider reference 或外部連線資料。

| T1 必交 evidence | 狀態 |
|---|---|
| pinned full SHA、route 與 fixture version | [TODO: 待 T1 確認] |
| 1440×900 與 390×844 render | [TODO: 待 T1 確認] |
| keyboard、ARIA-live、reduced-motion | [TODO: 待 T1 確認] |
| customer journey：entry → subscription status → `manual_review`／`owner_gate` → parse／queue fail-closed | [TODO: 待 T1 確認] |

## 保留 Gate

付款方式 vault／tokenization、provider callback、payment method persistence migration、正式 sandbox、稅務／電子發票憑證與 OAuth 均不在此 integration baseline 的可用範圍。這些項目在 owner 核准前維持 `BLOCKED`，不得藉由 T1 Demo 或 fixture 變成正式服務。
