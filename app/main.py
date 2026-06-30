"""FastAPI 入口（PR-1：基礎架構 + health；業務路由於 PR-2/PR-3 掛載）。"""
from datetime import datetime, timezone

from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# PR-2/PR-3 將在此掛載：
# from app.routers import auth, users, orders, ai_extract, billing, preferences
# app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
# ...
