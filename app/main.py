"""FastAPI 入口（PR-2：掛載業務路由）。"""
from datetime import datetime, timezone

from fastapi import FastAPI

from app.api.v1 import auth, orders, superadmin, webhook
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(webhook.router, prefix="/api/webhook", tags=["webhook"])
app.include_router(orders.router, prefix="/api/orders", tags=["orders"])
app.include_router(superadmin.router, prefix="/api/superadmin", tags=["superadmin"])
