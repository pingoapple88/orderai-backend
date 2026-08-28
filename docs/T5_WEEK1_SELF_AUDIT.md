# T5 Week 1 自審與整合交接

**Work Order：** `WO-T5-ORDERAI-SELF-SERVICE-UI-WEEK1`
**Screen Contract：** `ORDERAI-UI-W2-01`
**Feature Branch：** `feat/t5-orderai-demo-screen-contract`
**Evidence Level：** `MOCK`

## 交付範圍

本次交付是供 T1 掛載的 OrderAI **Screen View Model、全合成 fixture、五語系 key、local-only renderer、CSS、互動 script 與離線 harness**。T5 不直接接入正式後端；T1 應依交接 contract 在統一 AppShell 實際掛載三個 screen 與本地 assets。

| screen_id | contract | fixture 支援狀態 |
|---|---|---|
| `orderai.parse_result` | `src/ui/contracts/orderai/orderai.parse_result.json` | `success`、`needs_review`、`error`、`empty`、`blocked` |
| `orderai.risk_review` | `src/ui/contracts/orderai/orderai.risk_review.json` | `success`、`needs_review`、`manual_review`、`blocked` |
| `orderai.queue` | `src/ui/contracts/orderai/orderai.queue.json` | `processing`、`blocked`、`empty`；dedup、retry、dead-letter |

## L0／L1 自審

| 項目 | 結果 | 證據 |
|---|---|---|
| A1 基線與分支 | PASS | 本分支以 `feat/orderai-parse-self-service-hardening@99279894d347f2dd2d19a07735d7e937e0547f39` 為祖先基線。 |
| A2 保護分支與歷史 | PASS | 僅推送 `feat/t5-orderai-demo-screen-contract`；未修改 main、未 rebase 或 force-push。 |
| A3 Git identity | PASS | `pingoapple88 <pingoapple88@users.noreply.github.com>`。 |
| A4 去影子化 | PASS | 新增 assets／adapter／fixture 掃描無平台 SDK、endpoint、追蹤或隱藏識別。 |
| A5 設定與秘密 | PASS | 無新增 runtime 設定、正式 URL 或 secret。 |
| B1／B2 變更邊界 | PASS | 新增內容限於 `src/ui`、`src/adapters/orderai_adapter.py`、`tests/ui/orderai` 與 T5 文件。未變更 OAuth、migration、核心事件或正式 service。 |
| B3／B4 工作樹與產物 | PASS | 提交前清除可再生快取；未追蹤 SQLite、pyc 或 secret artifact。 |
| C1 focused tests | PASS | `python3 -m pytest -q tests/ui/orderai/test_orderai_ui_harness.py tests/ui/orderai/test_orderai_screen_renderer.py tests/test_demo_orderai_contract.py`：12 passed，exit 0。 |
| C2 受影響測試 | PASS | local-only renderer、CSS、互動 script 與 fixture 沒有 backend runtime／DB 相依；上述 harness 為完整受影響範圍。 |
| C3／C4 | PASS | `python3 -m compileall -q src tests/ui/orderai` 與 `git diff --check` 均 exit 0。 |
| C5 inherited failures | PASS | 本輪 focused harness 無失敗；既有 OAuth baseline blocker 維持於獨立 Auth 範圍，未在本次測試或 diff 出現。 |
| C6 狀態覆蓋 | PASS | fixture 涵蓋 success、empty、error、needs_review、manual_review、processing、blocked、timeout retry、dead-letter、duplicate。 |
| D1 Adapter | PASS | `OrderAIDemoAdapter` 只讀取版本化本機 JSON，不含網路、Provider、Queue 或資料庫操作。 |
| D2 company scope | PASS | UI fixture／view model 完全不接受或顯示 `company_id`、`store_key` 或 client tenant scope。 |
| D3 audit | PASS | 每個 state model 有非識別性的 `audit_reference`。 |
| D4 UTC／minor units | PASS | `updated_at` 為 UTC；金額僅以整數 `amount_minor` 呈現。 |
| D5 dedup／retry | PASS | fixture 與 harness 驗證 duplicate blocked、有限 retry 與 dead-letter；dead-letter 的人工重試標示 `requires_confirmation: true`。 |
| D6 event contract | PASS | 未新增或變更 Contract v1.8 事件。 |
| D7／D8 fail-closed 與 PII | PASS | 0.84、未匹配、provider timeout、dead-letter、duplicate 均非自動核准；fixture、adapter 不含未遮蔽 PII。 |
| E1／E2 | PASS | 所有 contract action 有穩定 ID 與結果狀態；六條全合成情境覆蓋各安全結果。 |
| E3 | PASS | `zh-Hant-TW`、`en-US`、`th-TH`、`ja-JP`、`id-ID` 的 key set 完整相同；未知 locale fallback `zh-Hant-TW`。 |
| E4／E5 畫面與互動 | HANDOFF_READY | 本地 `OrderAIScreenRenderer`、CSS 與互動 script 已產出可近用 HTML fragment、status／DemoBadge、ARIA live、target focus 與 dead-letter ConfirmDialog；T1 接入後仍須提供 1440×900、390×844 與瀏覽器實跑證據。 |
| E6 | PASS | 全部 model 固定 `mode: DEMO_MOCK`、`evidence_level: MOCK`、`formal_connection: false`。 |
| E7 | PASS | `src/ui` 與 adapter 外連／CDN／tracking 掃描 0 matches。 |

## 掃描結果

| 掃描 | 結果 |
|---|---|
| 受保護路徑：OAuth、migration、Docker、環境設定 | 0 changed paths |
| fixture／adapter：HTTP、Provider、Queue、DB URL | 0 matches |
| fixture／adapter：company、store、reply token、email、電話長數字 | 0 matches |
| 平台／CDN／追蹤字樣 | 0 matches |
| JSON syntax | 全部 contract、fixture、locale 均通過 `python3 -m json.tool` |

## T1 交接內容

T1 必須以 `src/ui/fixtures/orderai/orderai_screen_scenarios.json` 及 `OrderAIDemoAdapter` 渲染三個 screen，僅使用 `DEMO_MOCK`。建議入口為 `/demo/orderai/parse`、`/demo/orderai/risk-review`、`/demo/orderai/queue`。任何 unknown locale 必須由 adapter 回退至 `zh-Hant-TW`；consumer 需要 camelCase 時，只能在 T1 的 UI adapter 邊界轉換。

## 未完成與下一步

| 類型 | 項目 |
|---|---|
| TODO | T1 取得本次 local renderer、fixture 與互動 assets 後，於統一 Demo AppShell 完成三條路由、桌機／手機畫面與客戶旅程 evidence。 |
| BLOCKED | 正式 LLM／LINE／Redis／PostgreSQL、OAuth PR 合併、main merge、部署及正式資料均不在本次 T5 範圍。 |
| Next action | T1 將本文件與 fixture 加入其 pinned manifest；T5 接收整合回饋後只修正本分支的 screen contract／fixture／harness。 |
