"""FastAPI 入口。路由對齊 API 契約 v1.0（/api/v1 前綴 + store-scoped 訂單）。"""
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import auth, orders, webhook  # ※ superadmin 屬 /admin 紅線，本期不掛載
from app.core.config import get_settings
from app.core.response import error_response

settings = get_settings()
app = FastAPI(title=settings.app_name)

_STATUS_CODE = {
    400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
    404: "NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
}


@app.exception_handler(StarletteHTTPException)
async def _http_exc_handler(request: Request, exc: StarletteHTTPException):
    code = _STATUS_CODE.get(exc.status_code, "ERROR")
    return error_response(code, str(exc.detail), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def _validation_exc_handler(request: Request, exc: RequestValidationError):
    return error_response("VALIDATION_ERROR", "Request validation failed", status_code=422)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(webhook.router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(orders.router, prefix="/api/v1/stores/{store_id}/orders", tags=["orders"])
