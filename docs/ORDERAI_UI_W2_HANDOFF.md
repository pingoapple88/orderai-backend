# OrderAI UI W2 交接說明

**契約版本：** `ORDERAI-UI-W2-01`
**Feature ID：** `orderai`
**模式／證據等級：** `DEMO_MOCK`／`MOCK`

本交接包只含本機合成 Screen View Model、五語系字典與 focused harness。它不建立網路連線、不呼叫 Provider、不存取 Queue、LINE、Redis 或資料庫，亦不包含 OAuth、支付、發票、真實客戶資料或正式服務設定。

## Screen registry

| screen_id | T1 建議入口 | 主要狀態 | 合成操作 |
|---|---|---|---|
| `orderai.parse_result` | `/demo/orderai/parse` | `success`、`needs_review`、`error`、`empty`、`blocked` | 解析結果與整數 `amount_minor` 顯示 |
| `orderai.risk_review` | `/demo/orderai/risk-review` | `success`、`needs_review`、`manual_review`、`blocked` | 顯示 0.85 閾值、原因與未匹配品項 |
| `orderai.queue` | `/demo/orderai/queue` | `processing`、`blocked`、`empty` | 顯示 dedup、有限 retry 與 dead-letter；人工重試必須先確認 |

## 交接檔案

| 用途 | 路徑 |
|---|---|
| 三個 JSON Screen View Model 契約 | `src/ui/contracts/orderai/` |
| 全合成情境資料 | `src/ui/fixtures/orderai/orderai_screen_scenarios.json` |
| 五語系 key／文案 | `src/ui/locales/orderai/` |
| T1 可引用的無外連轉換層 | `src/adapters/orderai_adapter.py` |
| 可嵌入 T1 AppShell 的本地畫面 renderer、CSS、互動 | `src/ui/screens/orderai/` |
| focused harness | `tests/ui/orderai/test_orderai_ui_harness.py` |

## 固定安全邊界

所有跨 Team fixture 使用 `snake_case`；若前端框架需要 camelCase，只能在其 UI adapter 邊界轉換。`company_id`、`store_key`、使用者識別、電話、地址、email、reply token 與正式內部識別一律不在 screen model 或 fixture 出現。每個狀態變更保留非識別性的 `audit_reference`；金額只使用整數 `amount_minor`；時間只使用 UTC。

`dead_letter` 不可自動重送，唯一提供的 `orderai.manual_retry` action 必須帶 `requires_confirmation: true`。`needs_review`、未匹配品項、低信心、逾時與重複事件均不可在 Demo UI 顯示為已核准。

`parse_success` 情境顯示去識別化的合成輸入摘要，並以 `result_state: loading` 呈現使用者啟動解析後的載入回饋。只有 `risk_score: 0.86`、型錄命中與證據完整的情境可呈現 `approval_state: approved`；0.84 與未匹配情境維持 `needs_review`。

## 嵌入方式

T1 以 `OrderAIScreenRenderer().render_scenario(scenario_id, locale)` 取得三個可近用的 HTML fragment，並載入 `orderai_screens.css` 與 `orderai_screen_interactions.js`。所有 action 會提供合成結果回饋；`orderai.manual_retry` 只會先顯示確認對話框，確認後才顯示 `processing`，不會觸發網路、Provider、Queue 或資料庫操作。
