# T5 OrderAI 唯一 integration baseline

本文件定義 T1 掛載 OrderAI synthetic presentation 的唯一來源：`feat/orderai-self-service-subscriptions` 的 **final pinned HEAD**。T1 必須從共享整合 Manifest 的 T5 row 取得該次推送的完整 SHA；不得混用不同 branch、未推送工作樹、OAuth 修正 branch 或 StallPay-V2 payment／invoice core。

| 範圍 | 來源 asset | reuse_mode | T1 呈現界線 |
|---|---|---|---|
| 獨立銷售入口、三通路、訂閱、entitlement、帳務、發票 | `orderai.subscription_lifecycle`／`ORDERAI-SUBSCRIPTION-W2-01` | `REUSE_AS_IS` | 僅 `DEMO_MOCK`；未知付款／發票為 `manual_review`。 |
| AI 額度、帳務 history、invoice history、sandbox／cost／backup／EventBus readiness | `orderai.operations_readiness`／`ORDERAI-OPERATIONS-W2-01` | `REUSE_AS_IS` | 僅 local mock／mapping-only；backup 為 `owner_gate`。 |
| 付款方式管理 | `orderai.payment_method_management`／`ORDERAI-PAYMENT-METHOD-W2-02` | `INTEGRATE_VIA_ADAPTER` | 查看僅有無憑證 synthetic summary；新增、切換、修改、重新授權、解除綁定、移除均為 `owner_gate`，unknown／timeout 為 `manual_review`；不可收集 payment token、卡號或帳戶資料。 |
| 電子發票憑證 | `orderai.integration_entry`／`ORDERAI-INTEGRATION-W2-04` | `INTEGRATE_VIA_ADAPTER` | 沿用 `IInvoiceProvider.issue` 的 status-only projection；憑證、reference、下載 URL 與 provider payload 均不公開，且 credential access 為 `owner_gate`。 |
| parse result | `orderai.parse_result`／`ORDERAI-PARSE-RESULT-W2-01` | `REUSE_AS_IS` | 高信心 matched 才是 `approved`；低信心、unmatched、provider error／timeout 都是 `needs_review`，僅顯示紅遮罩預覽與 hash-only audit reference。 |
| risk review | `orderai.risk_review`／`ORDERAI-RISK-REVIEW-W2-01` | `REUSE_AS_IS` | 沿用 0.85 inclusive threshold；未匹配、缺價、provider failure與資料疑義只能 `needs_review`，scope 不可得則 `blocked`。 |
| Queue／dead-letter | `orderai.queue`／`ORDERAI-QUEUE-W2-01` | `REUSE_AS_IS` | 沿用 server-derived line-event hash 去重與非變異 limited retry；超限僅進 dead letter／`manual_review`。 |
| 智慧農業展 synthetic flow | `orderai.smart_agri_expo`／`ORDERAI-SMART-AGRI-EXPO-W2-01` | `INTEGRATE_VIA_ADAPTER` | 農產團購、AI parse、risk／needs_review、即期品建議、FAQ／客服、subscription、payment、invoice與entitlement均為五語系 `DEMO_MOCK`；AI／客服不得讀取未授權 PII，所有疑義須人工審查。 |

## T1 input

T1 的入口為 `orderai.integration_entry`（`ORDERAI-INTEGRATION-W2-05`），fixture 為 `src/ui/fixtures/orderai/orderai_integration_entry.json`。解析、風險覆核與Queue的獨立來源分別為 `orderai.parse_result`、`orderai.risk_review`、`orderai.queue` 及其同名 fixture。這些資產以五個 locale 對應 direct、dealer、enterprise 與 fail-closed 狀態，且不包含真實使用者、公司、店家、付款、發票、卡號、帳戶、token、provider reference 或外部連線資料。

| T1 必交 evidence | 狀態 |
|---|---|
| pinned full SHA、route 與 fixture version | [TODO: 待 T1 確認] |
| 1440×900 與 390×844 render | [TODO: 待 T1 確認] |
| keyboard、ARIA-live、reduced-motion | [TODO: 待 T1 確認] |
| customer journey：entry → subscription status → `manual_review`／`owner_gate` → parse／queue fail-closed | [TODO: 待 T1 確認] |

## 保留 Gate

付款方式 vault／tokenization、provider callback、payment method persistence migration、正式 sandbox、稅務／電子發票憑證與 OAuth 均不在此 integration baseline 的可用範圍。這些項目在 owner 核准前維持 `BLOCKED`，不得藉由 T1 Demo 或 fixture 變成正式服務。
