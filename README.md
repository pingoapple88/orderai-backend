# OrderAI Backend

OrderAI（orderai.merchcore.ai）— JiiMoo 集團 AI 訂單辨識平台後端。

技術棧（集團主權守則 · 技術棧白名單）：**Python 3.11+ · FastAPI · SQLAlchemy 2.0 · PostgreSQL**。

> 本 Repo 於 PR-1 由 Node.js/Express 重構為 Python FastAPI。開發規範見 `CLAUDE.md`。

## 目錄結構
```
app/
  core/           設定、DB、安全、事件、抽象介面
  models/         SQLAlchemy ORM（對應 schema.sql 9 張表）
  providers/      LINE / LLM Adapter 實作
  routers/        API 路由（PR-2/PR-3 實作）
  schemas/        Pydantic schema（PR-2/PR-3）
  main.py         FastAPI 入口
alembic/          資料庫遷移（0001 套用 schema.sql）
tests/            pytest
```

## 本機啟動
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # 填入實際值
alembic upgrade head          # 建表
uvicorn app.main:app --reload --port 8000
# 健康檢查
curl http://localhost:8000/health
```

## Docker
```bash
docker compose up --build     # 起 postgres + api，自動 alembic upgrade
```

## 部署版本識別

部署系統必須將目前映像對應的完整 Git SHA 注入 `RELEASE_SHA`；API 的
`GET /health` 會回傳 `releaseSha`，用來對照 staging 與正式 API 實際運行的
版本。未設定時明確回傳 `unknown`，不以本機或推測的 SHA 冒充部署版本。

```bash
RELEASE_SHA="$GIT_COMMIT_SHA" uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health
# {"status":"ok","timestamp":"...","releaseSha":"<40-char-sha>"}
```

API、app、RQ Worker 與 Scheduler 的 release SHA 必須一致，才可進行切換或
回滾判定。`RELEASE_SHA` 不是 secret，不可改用任何 credential 或連線字串。

## 測試
```bash
pytest
```

## 訂單解析與風險守衛

業務流程僅依賴 `ILLMProvider`，模型協定由 `LLM_PROVIDER` 選擇。`http_chat`、`ollama` 與 `anthropic` 均以 HTTP Adapter 封裝；端點、模型名稱、API Key、逾時與其他外部設定必須由部署環境注入，缺少必要設定時會拒絕解析而不建立訂單。

解析結果只有同時符合下列條件才會自動建立 `pending_confirm` 訂單：整體與每個商品列的信心分數皆不低於 `AI_CONFIDENCE_THRESHOLD`、每列保留原文證據、數量在設定範圍內，以及所有商品均精確命中該店有效型錄。任一條件未通過時，Worker 會轉人工確認，並在 `audit_logs` 記錄決策代碼、模型識別、信心、門檻與原文 SHA-256；原始 LINE 訊息與電話不會寫入稽核 JSON。

`plans` 使用 `channel` 區分 `direct`、`dealer`、`enterprise`。同名方案可依通路分別定價；實際價格、推廣來源與經銷服務費規則仍由產品與訂閱流程負責。

## 解析準確率評測

使用去識別化 JSONL 標註資料評測商品加數量的 exact match、precision、recall 與 F1；未提供標註資料時不得主張已達特定準確率。

```bash
python scripts/evaluate_order_parser.py path/to/labelled-orders.jsonl \
  --minimum-exact-match 0.95
```

每一列資料的格式如下：

```json
{"expected":[{"product_name":"蘋果","quantity":2}],"actual":[{"product_name":"蘋果","quantity":2}]}
```

## Phase 1 範圍
- **PR-1（本次）**：基礎架構 — 清除 Node 殘碼、Python 骨架、9 張表 ORM、Alembic、Docker、抽象介面。
- PR-2：LINE OAuth + JWT + 訂單 CRUD + audit_logs。
- PR-3：ILLMProvider + AI 解析 + 信心閾值 + 額度扣除。
