# OrderAI Phase 1 MVP — CCM 開發指令包

> 本文件是交給 **Claude Code Max（CCM / Opus）** 執行的完整開發授權書。
> CCM 擁有足夠的 Context 視窗，請**一次讀取整個 Repo**，自主判斷現有程式碼的問題，並依照本文件的規範從零重構。

---

## 專案背景

**Repo**：`pingoapple88/orderai-backend`（已 clone 到本機）

**現況問題**：目前 `main` 分支存在 Node.js + Express 的實作，這**完全違反 Jiimoo 集團主權守則的技術棧白名單**（規定必須使用 Python FastAPI + SQLAlchemy + PostgreSQL）。現有的 `src/`、`package.json`、`package-lock.json`、`node_modules/` 等 Node.js 相關檔案必須全部清除。

**需要保留的資產**：
- `schema.sql`（9 張資料表的 PostgreSQL DDL，是資料庫設計的唯一依據）
- `.env.example`（需更新為 Python 版本）
- `README.md`（需重寫）

---

## 治理規範（強制遵守）

本專案受 Jiimoo 集團「雙層治理規範」約束，CCM 在每一個決策點都必須對照以下規則：

**第一層：集團主權守則（7 條）**

| 守則 | 要求 |
| :--- | :--- |
| 平台中立 | 所有外部服務（LINE、LLM）必須透過 Adapter 抽象，嚴禁直接呼叫 |
| 原始碼主權 | 所有程式碼必須 commit 到 `pingoapple88/orderai-backend` |
| 標準化部署 | 必須提供 Dockerfile、docker-compose.yml、.env.example、Alembic migration |
| 技術棧白名單 | 僅使用 Python FastAPI + SQLAlchemy + PostgreSQL，禁止 Node.js / TypeScript |
| 資料主權 | 資料庫指向 Railway PostgreSQL，禁止寫入任何第三方雲端 |
| AI 服務可替換 | LLM 呼叫必須透過 `ILLMProvider` 介面，支援切換 OpenAI / Claude / Ollama |
| 強制主權檢核 | 每次 PR 必須附上七項主權檢核逐項回答 |

**第二層：技術治理框架（8 條鐵律）**

1. 抽象介面優先：`IAuthProvider`、`ILLMProvider`、`INotificationProvider`
2. 外部化設定：所有 API Key、閾值從 ENV 讀取，使用 `pydantic-settings`
3. RBAC 最小權限：每個 API 第一行驗權，所有查詢帶 `user_id`
4. 稽核可追溯：所有狀態變更寫入 `audit_logs` 表
5. 事件驅動：模組透過 EventBus 解耦（Phase 1 可用簡單的 in-process event dispatcher 先行）
6. 白標可擴展：UI 走 i18n，租戶可 override 設定
7. 全球合規：金額用整數分位（TWD 以分為單位）、時間 UTC、PII 欄位加密
8. AI 自動化優先：信心閾值控制、fail-closed、AI 決策有 log

---

## Phase 1 MVP 功能範圍

Phase 1 的目標是建立一個可在 Railway 上獨立運行的 Python FastAPI 後端，支援以下核心功能：

**核心功能清單：**

| 模組 | 功能 | 對應資料表 |
| :--- | :--- | :--- |
| 認證 | LINE OAuth 2.0 登入、JWT 核發與驗證 | `users` |
| 訂單 | 訂單 CRUD（建立、查詢、更新狀態） | `orders`, `order_items` |
| AI 解析 | 接收文字/截圖，呼叫 LLM 解析為結構化訂單 | `ai_extractions`, `ai_usage_logs` |
| 帳務 | 查詢用戶帳務紀錄 | `billing_records` |
| 偏好設定 | 讀取與更新用戶偏好 | `user_preferences` |
| 稽核 | 所有寫入操作自動記錄 | `audit_logs` |

---

## 目標目錄結構

請依照以下結構重建整個 Repo：

```
orderai-backend/
├── app/
│   ├── core/
│   │   ├── interfaces/
│   │   │   ├── auth_provider.py      # IAuthProvider ABC
│   │   │   └── llm_provider.py       # ILLMProvider ABC
│   │   ├── config.py                 # pydantic-settings 設定
│   │   ├── database.py               # SQLAlchemy engine & session
│   │   ├── security.py               # JWT 工具函式
│   │   └── events.py                 # 簡易 EventBus
│   ├── models/                       # SQLAlchemy ORM 模型（對應 schema.sql 的 9 張表）
│   ├── providers/
│   │   ├── line_auth.py              # IAuthProvider 的 LINE 實作
│   │   └── openai_llm.py             # ILLMProvider 的 OpenAI 實作
│   ├── routers/
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── orders.py
│   │   ├── ai_extract.py
│   │   ├── billing.py
│   │   └── preferences.py
│   ├── schemas/                      # Pydantic request/response schemas
│   └── main.py                       # FastAPI app 入口
├── alembic/                          # Alembic 遷移腳本
├── tests/                            # pytest 測試（至少覆蓋 auth 與 order 的 happy path）
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── CLAUDE.md                         # 本文件（保留在 Repo 中作為開發規範）
└── README.md
```

---

## 執行計畫（PR 拆分）

請依照以下順序分批提交，**不得在前一個 PR 合併前開啟下一個 PR**：

**PR-1：基礎架構（feat/pr-1-infrastructure）**
清除 Node.js 殘碼 → 建立 Python 專案骨架 → SQLAlchemy 模型 → Alembic 初始化 → Dockerfile + docker-compose → 抽象介面定義 → 更新 .env.example 與 README

**PR-2：認證與訂單（feat/pr-2-auth-orders）**
LINE OAuth 2.0 實作 → JWT 驗證 Dependency → 訂單 CRUD → audit_logs 寫入 → pytest 基礎測試

**PR-3：AI 解析（feat/pr-3-ai-extraction）**
ILLMProvider OpenAI 實作 → /api/ai/extract 端點 → 信心閾值控制 → ai_usage_logs 扣額 → fail-closed 錯誤處理

---

## 每次 PR 必附：七項主權檢核

完成每個 PR 後，在 PR 描述中逐項回答以下問題（答「是」或「否」並附說明）：

1. 程式碼是否已 commit 到 `pingoapple88/orderai-backend`？
2. 是否僅使用 Python FastAPI + SQLAlchemy + PostgreSQL？
3. 是否包含 Dockerfile、docker-compose.yml、.env.example 與 migration 腳本？
4. 所有外部服務是否皆透過 Adapter 介面呼叫？
5. 每個 API 是否皆有驗權，且查詢皆帶 `user_id`？
6. 狀態變更是否皆已寫入 `audit_logs`？
7. API Key 等敏感資訊是否皆從環境變數讀取？

---

## 重要提示

CCM 在執行過程中若遇到以下情況，請**暫停並向使用者確認**，不得自行決定：

- 需要修改 `schema.sql` 中已定義的資料表結構（欄位新增/刪除/型別變更）
- 需要引入 `schema.sql` 以外的第三方服務（如 Redis、S3 等）
- 商業邏輯不明確（如 AI 額度扣除的邊界條件、訂單狀態機的轉換規則）
