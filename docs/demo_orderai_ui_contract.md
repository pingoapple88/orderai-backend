# OrderAI Demo UI Screen Contract

**版本：** `DEMO-UI-W2-01`
**供應範圍：** T1 Demo UI 整合
**資料來源：** `tests/fixtures/demo_orderai.json`
**資料性質：** 全部為 Demo／合成資料；不可向任何正式 API、Queue、LINE、LLM、Redis 或資料庫發出請求。

## 1. 整合目的與邊界

T1 應以 fixture 直接渲染 OrderAI 的 Demo 畫面，而不是把 fixture 當作可呼叫的後端端點。畫面必須讓使用者輸入或選擇一段**合成**訂單文字、啟動模擬解析、看到風險結果與 Queue 狀態，並可在重試、dead-letter 與返回功能總覽之間操作。

> 所有畫面頂端或狀態列必須顯示「Demo／合成資料」。`Demo mock` 不代表已接通任何正式交易、外部 Provider 或背景工作者。

本契約不包含登入狀態驗證、付款、發票、金流、定價、資料庫寫入或真實訊息傳送；既有登入安全修正範圍完全不屬於本次 Demo 交付。

## 2. 固定 locale 與 fallback

T1 的 locale picker 只能顯示下列五種代碼；fixture 未包含也不得自行加入其他代碼。未知 locale 一律回退為 `zh-Hant-TW`。

| locale | 顯示名稱 | `demoBadge` |
|---|---|---|
| `zh-Hant-TW` | 繁體中文 | Demo／合成資料 |
| `en-US` | English | Demo / Synthetic data |
| `th-TH` | ไทย | เดโม / ข้อมูลสังเคราะห์ |
| `ja-JP` | 日本語 | デモ／合成データ |
| `id-ID` | Bahasa Indonesia | Demo / Data sintetis |

## 3. 畫面區塊與最小資料契約

| 畫面區塊 | fixture 欄位 | 使用者可見行為 | 可近用性要求 |
|---|---|---|---|
| Header 狀態列 | `meta`, `localeLabels.*.demoBadge` | 顯示產品名稱、版本、Demo badge、locale picker、返回功能總覽 | badge 具有可讀文字；返回控制項可鍵盤聚焦 |
| 訂單文字輸入區 | `scenarios[].input` | 選取情境後帶入合成文字；「模擬解析」進入 loading | textarea 有 label；執行中以 `aria-busy` 表示 |
| 結果摘要 | `scenarios[].result` | 顯示整體風險分數、商品列、證據與型錄命中狀態 | 結果改變由 `aria-live="polite"` 宣告 |
| 風險狀態卡 | `scenarios[].risk` | 清楚顯示 `approved`、`needs_review`、`error` 或 `blocked` 及 reason codes | 色彩之外必須有狀態文字與圖示／標記 |
| Queue 面板 | `scenarios[].queue` | 顯示 `not_queued`、`queued`、`retrying`、`dead_letter` 或 `blocked`；只在 fixture 定義 action 時顯示操作鈕 | 按鈕具名稱；不可用狀態須用 `aria-disabled` 與原因文字 |
| PII 防護提示 | `scenarios[].privacy` | 顯示 queued payload 已遮蔽，不顯示原始識別資料 | 不得把任何未遮蔽值寫進 DOM、title、log 或 analytics |

所有 consumer-facing 欄位採 camelCase。畫面不可要求或顯示 `companyId`、`storeId`、`userId`、`replyToken`、內部 event ID、訂閱識別值、原始訊息或原始 PII。

## 4. 狀態與互動規則

| 觸發 | 預期畫面狀態 | 可操作控制項 | 禁止行為 |
|---|---|---|---|
| 初始開啟 | `empty` | 選情境、輸入合成文字、模擬解析 | 不顯示真實歷史訂單 |
| 模擬解析中 | `loading` | 返回功能總覽 | 重複提交、假稱已呼叫外部服務 |
| 0.86 且條件完整 | `success`、`approved`、`queued` | 查看 Queue、返回總覽 | 宣稱已建立正式訂單 |
| malformed 或 provider error | `error`、`needs_review` 或 `blocked` | 依 fixture 顯示重試或返回 | 自動通過風險閘門 |
| 0.84 | `needs_review` | 查看原因、返回總覽 | 顯示為已核准 |
| provider timeout 重試中 | `retrying` | 模擬重試、返回總覽 | 無限重試或自動建單 |
| retry 已耗盡 | `dead_letter`、`blocked` | 查看人工處理說明、返回總覽 | 把 dead-letter 顯示成成功 |

「模擬重試」只可在 `retryable: true` 且 `nextScenarioId` 存在時，切換到 fixture 指定的後續情境。所有情境切換均為前端記憶體操作，頁面重新整理後可回到 `empty`。

## 5. 八條合成垂直流程

| scenario ID | 用途 | 預期風險結果 | Queue 結果 | T1 操作 |
|---|---|---|---|---|
| `parse-success-086` | 完整合成訂單解析 | `approved`，風險分數 `0.86` | `queued` | 模擬解析 → 查看 Queue |
| `malformed-input` | 無法安全辨識的輸入 | `needs_review` | `blocked` | 模擬解析 → 檢視原因 |
| `risk-needs-review-084` | 低於閾值 | `needs_review`，風險分數 `0.84` | `not_queued` | 模擬解析 → 檢視原因 |
| `provider-error` | Provider 可重試錯誤 | `needs_review` | `retrying` | 模擬解析 → 模擬重試 |
| `provider-timeout` | Provider timeout | `needs_review` | `retrying` | 模擬解析 → 模擬重試 |
| `provider-timeout-dead-letter` | 有限重試耗盡 | `blocked` | `dead_letter` | 查看人工處理說明 |
| `pii-redacted-payload` | 已遮蔽的 Queue payload | `needs_review` | `queued` | 模擬解析 → 展開隱私提示 |
| `empty-state` | 初始或無品項情境 | `blocked` | `not_queued` | 選取另一個情境 |

## 6. fixture 欄位定義

| 欄位 | 型別 | 必要性 | 說明 |
|---|---|---:|---|
| `meta` | object | 是 | 版本、產品、Demo 標記與五語系 locale 集合。 |
| `localeLabels` | object | 是 | 五語系 UI label 最小字典。 |
| `scenarios` | array | 是 | 八種可被選取的合成流程。 |
| `scenarios[].id` | string | 是 | 穩定、前端可引用的 scenario ID。 |
| `scenarios[].state` | string | 是 | `empty`、`success`、`error`、`needs_review`、`retrying` 或 `blocked`。 |
| `scenarios[].input` | object | 是 | 僅含合成 `rawText` 與選擇 locale。 |
| `scenarios[].result` | object | 是 | 商品名稱、正整數數量、證據狀態、型錄命中與信心資訊；沒有金額欄位。 |
| `scenarios[].risk` | object | 是 | `status`、`riskScore`（可為 `null`）與非 PII reason codes。 |
| `scenarios[].queue` | object | 是 | Queue 顯示狀態、是否可重試與後續情境 ID。 |
| `scenarios[].privacy` | object | 是 | 已遮蔽 payload 範例與提示文字。 |

## 7. T1 實作驗收

T1 完成後，客戶可從功能總覽進入 OrderAI，使用任一 fixture 情境走完「輸入／選取 → 模擬解析 → 結果 → 風險與 Queue → 返回總覽」；每次操作都須有 loading、success、error、blocked 或 needs review 回饋。桌機 `1440×900` 與手機 `390×844` 不得水平溢出，須支援 keyboard、`focus-visible`、`aria-live` 及 `prefers-reduced-motion`。

T5 的 fixture contract tests 位於 `tests/test_demo_orderai_contract.py`。測試確認 fixture 為 Demo-only、五語系完整、八種必需情境齊備、Queue payload 不含未遮蔽 PII、未含價格或外部 URL，且不將登入安全或正式服務接入 Demo 流程。
