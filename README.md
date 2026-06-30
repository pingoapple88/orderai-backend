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

## 測試
```bash
pytest
```

## Phase 1 範圍
- **PR-1（本次）**：基礎架構 — 清除 Node 殘碼、Python 骨架、9 張表 ORM、Alembic、Docker、抽象介面。
- PR-2：LINE OAuth + JWT + 訂單 CRUD + audit_logs。
- PR-3：ILLMProvider OpenAI + AI 解析 + 信心閾值 + 額度扣除。
