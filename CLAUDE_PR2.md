# OrderAI Phase 1 MVP — PR-2 核心業務邏輯指令包

> 本文件是交給 **Claude Code Max（CCM / Opus）** 執行的 PR-2 開發指令書。
> 目的：實作 OrderAI 的核心業務邏輯（Auth、Webhook、Order、Payment Bridge），並落實四大極端情境的架構防禦機制。

---

## 專案背景與授權範圍

**目前狀態**：`pingoapple88/orderai-backend` 的 `main` 分支已完成 PR-1b（多租戶 schema + 金額整數化）。
**本次授權（PR-2）**：實作核心業務模組，並**必須**包含外部架構評估所要求的 Redis Queue 非同步處理、AI 成本防護與複合索引。

---

## 實作目標與防禦機制要求

### 1. 資料庫擴充（複合索引與全域設定表）
- **複合索引**：在所有業務表（orders, billing_records, ai_extractions, ai_usage_logs, audit_logs）建立以 `tenant_id` 為首的複合索引，確保 20 萬租戶規模下的查詢效能。
- **系統設定表**：建立 `system_settings` 表（`key`, `value`, `description`, `updated_at`），用來儲存所有不可寫死的關鍵參數（如 `ai_soft_limit_pro`, `pre_filter_regex`, `polling_interval` 等）。
- **要求**：請透過 Alembic migration 實作上述兩項變更。

### 2. Auth 與 SuperAdmin 模組
實作 `app/api/v1/auth.py`、`app/core/security.py` 與 `app/api/v1/superadmin.py`。
- **Auth 要求**：實作 `IAuthProvider` 介面的 LINE 登入邏輯。產生包含 `user_id`, `tenant_id`, `role` 的 JWT token（role 包含 admin, staff, superadmin）。
- **SuperAdmin 要求**：實作僅限 `role='superadmin'` 存取的 API，包含：(1) 修改 `plans` 表的定價與額度 (2) 修改 `system_settings` 的全域參數 (3) 查詢 Redis Queue 深度與 AI 使用量統計，以供監控流量與成本。

### 3. Webhook 模組與 Redis Queue（情境一防禦：極端流量）
實作 `app/api/v1/webhook.py` 與背景 Worker。
- **要求**：Webhook 端點收到 LINE 訊息後，**絕對不可**同步呼叫 LLM 或寫入 DB。必須將 Raw Payload 丟入 Redis Queue，並在 100ms 內回傳 `200 OK`。
- 實作一個獨立的 Worker 進程（如 Celery 或 RQ）來消化 Queue 訊息。

### 4. AI 解析模組與成本防護（情境二防禦：成本失控）
實作 `app/services/ai_service.py`。
- **要求**：在呼叫 LLM 前，實作**前置意圖預檢（Pre-filter）**。從 `system_settings` 讀取 `pre_filter_regex` 進行正則比對。若判定為閒聊，直接略過，不計入使用次數也不呼叫 LLM。
- **要求**：實作 Pro 方案的「軟限制（Soft Limit）」。從 `system_settings` 讀取 `ai_soft_limit_pro` 閾值，當月解析次數超過該值時觸發阻斷，避免成本無限上綱。所有設定值必須從 DB 讀取（可搭配 Redis 快取），**絕對不可寫死在程式碼中**。

### 5. Order 模組與計稅合規（情境三防禦：日本發票合規）
實作 `app/api/v1/orders.py` 與 `app/services/order_service.py`。
- **要求**：實作訂單 CRUD，所有查詢必須帶入 `tenant_id`。
- **要求**：實作日本市場（`market='jp'`）的專屬計稅邏輯，確保「一筆訂單只進行一次稅額四捨五入（對總金額計稅）」。必須為此撰寫獨立的單元測試。

### 6. Payment Bridge 與雙保險機制（情境四防禦：金流延遲）
實作 `app/providers/stallpay.py` 與 Cron Job。
- **要求**：完成 `StallPayProvider` 的具體實作。
- **要求**：實作**主動輪詢機制**。當訂單建立付款連結後，若 30 分鐘未收到 Webhook 回調，由 Cron Job 主動呼叫 StallPay API 查詢狀態並更新。所有狀態變更寫入 `audit_logs`。

---

## 執行計畫（PR-2）

請依序執行以下步驟，完成後提交為 PR-2。

### 1. 基礎設施擴充
- 更新 `docker-compose.yml`，加入 Redis 服務。
- 更新 `requirements.txt` / `pyproject.toml`，加入 Redis 與 Queue 套件（如 `celery` 或 `rq`）。

### 2. 資料庫 Migration
- 產生新的 Alembic migration，加入 `tenant_id` 複合索引。

### 3. 實作核心模組
- 依序實作 Auth, Webhook (含 Worker), AI Service (含 Pre-filter), Order (含 JP 計稅), Payment Bridge (含 Polling)。

### 4. 撰寫測試
- 必須包含：Webhook 快速回應測試、AI Pre-filter 攔截測試、日本計稅邏輯單元測試。

### 5. 提交 PR-2
- 建立分支：`feat/pr-2-core-modules`
- 執行 `pytest` 確認所有測試通過。
- 將變更 commit 並推送到遠端。

---

## 執行提示 (給 Claude Code)

1. **架構優先**：PR-2 的重點在於落實四大防禦機制，請確保 Redis Queue 與 Pre-filter 的邏輯健壯。
2. **多語言準備**：錯誤訊息請預留 i18n 骨架（支援 zh-TW 與 en），具體字串可先寫死或用簡單的字典。
3. **完成後回報**：請在 PR 描述中說明四大防禦機制的實作細節，並附上 `pytest` 執行結果與七項主權檢核回答。
