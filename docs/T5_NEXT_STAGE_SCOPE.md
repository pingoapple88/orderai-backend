# Team 5：OrderAI 下一階段範圍

**分支：** `feat/orderai-parse-self-service-hardening`
**基線：** `3131a2cb752efb713fe4b0e50e0d6f7fe9b5e3f6`
**目標狀態：** `FEATURE_READY_FOR_INTEGRATION_PENDING_AUTH_BASELINE`

## 本輪允許修改路徑

| 領域 | 允許路徑 | 目的 |
|---|---|---|
| 解析可靠性 | `app/services/parse_evaluation.py`、`app/services/ai_service.py`、必要時 `app/services/parse_normalizer.py`、`app/schemas/parse.py` | malformed input、quantity、Unicode 商品比對、integer cents 與 fail-closed。 |
| 自助服務 | `app/api/v1/module.py`、`app/services/module_service.py`、`app/adapters/merchcore_module.py`、`app/schemas/__init__.py` | company scope、冪等、通路、最小公開回應與選項 B 服務狀態。 |
| 風險與 Provider | `app/services/order_risk_service.py`、`app/services/ai_service.py`、`app/providers/failover_llm.py`、`app/providers/http_chat_llm.py`、`app/core/interfaces/llm_provider.py`、`app/services/settings_service.py` | 0.85 閘門、error／timeout、fallback 與可替換 Provider。 |
| LINE／Queue | `app/api/v1/batches.py`、`app/api/v1/webhook.py`、`app/workers/line_worker.py`、`app/worker.py`、`app/scheduler.py`、`app/providers/queue_memory.py`、`app/providers/queue_redis.py`、`app/core/interfaces/queue.py`、`app/services/batch_service.py` | 合成 webhook、去重、retry metadata、needs_review 與 mock Queue workflow。 |
| 五語系與 PII | `app/services/pii_redaction.py`、`app/core/i18n.py`、Module API／manifest、`.env.example`、`README.md` | 正式 locale、共用 redact 邊界與安全設定說明。 |
| 測試／證據 | `tests/`、`evidence/` | 使用合成資料覆蓋解析、風險、Provider、PII、Queue、company scope、冪等與驗收原始輸出。 |

## 強制行為

所有外部 Provider 僅能以 mock 或 adapter contract 驗證。模型、端點、timeout、retry、閾值與任何外部服務設定均從 ENV 取得。解析輸入、模型 payload 與 AI audit 需要共用 `redact_pii()`；不允許原始電話、email、識別碼或未遮蔽訂單文字進入模型或 audit。

所有金額使用 integer minor units／cents。解析無法建立安全且可驗證的商品、數量、價格、原文證據或信心結果時，必須轉為 `needs_review` 或 `provider_error`，不得自動建單。`confidence < 0.85` 必須 `needs_review`；`confidence = 0.85` 的既有規則需以測試固定；只有高於門檻且型錄、數量、證據皆完整時才可進 `approved`。

Module self-service 採選項 B：只保存 `pending_activation` 服務狀態及去識別化 audit。所有受保護 route 先驗證 server-side principal；company scope 不可由 query、URL 或 request body 指定。公開回應不得含內部識別碼、event id、subscription id、PII ciphertext 或未遮蔽來源內容。

正式 locale 僅限：`zh-Hant-TW`、`en-US`、`th-TH`、`ja-JP`、`id-ID`。五種 locale 都必須有可執行的 PII、fallback 或 API fixture；未知 locale 依既有 fallback 行為處理並有測試。

只允許使用治理已核准的四類核心事件名稱；本輪不發生模組生命週期事件，也不新增第五類事件。任何未定義 event 或 transport 必須維持不發送，不可自行補名或建立 outbox。

## 明確禁止

本輪不得修改、夾帶或假定已合併 PR #22 的內容；不得修改 PR #21 base、rebase 或 force push 既有分支。不得新增 migration、變更正式 Auth schema、支付、發票、分潤、正式外部服務、正式部署、DNS、真實客戶資料、正式 LINE／LLM／Redis／PostgreSQL 憑證或任何未核准事件。

本輪不得宣稱 Production Ready 或已部署。完成條件是 focused suite 的合成可丟棄環境證據與 `FEATURE_READY_FOR_INTEGRATION_PENDING_AUTH_BASELINE`；在獨立 OAuth PR 經 review 合併到 main 後，才可以新 main SHA 建立 staging 驗證分支，重跑完整測試與分離環境驗證。

## staging 依賴

| 依賴 | staging 前需取得的證據 |
|---|---|
| 版本一致性 | API、app、Worker、Scheduler 的同一 release SHA。 |
| 資料庫 | revision、備份、W1／W2 migration preflight、fresh／upgrade／rollback 結果。 |
| Queue | Redis／RQ health、queue depth、retry／dead-letter 策略及 job drain。 |
| LINE | 測試 Channel 的 OAuth、webhook、去重與 callback 流程。 |
| AI | 合成 Provider error／timeout／fallback，加上去識別化盲測資料。 |
| 方案 | 已核定的通路、價格版本日期與對外文案；本輪不提供或猜測價格。 |
