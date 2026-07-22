"""FastAPI 入口。路由對齊 API 契約 v1.0（/api/v1 前綴 + store-scoped 訂單）。"""
import logging
import sys
import traceback
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import auth, batches, orders, products, webhook  # ※ superadmin 屬 /admin 紅線，本期不掛載
from app.core.config import get_settings
from app.core.response import error_response

# debug（暫時）：讓應用層 log 與未處理例外 traceback 進 stdout（Railway 一定捕捉 stdout）。
# PYTHONUNBUFFERED 只影響 print，不影響 logging；uvicorn/應用 logger 需自行配 handler。
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

settings = get_settings()
app = FastAPI(title=settings.app_name)

# CORS：前端(正式 app)跨來源打 /api/v1/*，需放行來源 + Authorization header(Bearer)。
# 只放行正式 app 網域；不放行 pages.dev / LP。用 Bearer token(非 cookie)，故不開 credentials，
# 也就不觸犯「allow_origins=['*'] + allow_credentials=True」的錯誤組合。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.orderai.merchcore.ai"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

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


@app.exception_handler(Exception)
async def _debug_exc_handler(request: Request, exc: Exception):
    # ⚠️ DEBUG ONLY — 診斷完立刻 revert，勿長留（會外洩內部結構/traceback）。
    # FastAPI 的 @app.exception_handler(Exception) 會被 ServerErrorMiddleware 當 handler，攔得到未處理例外。
    return PlainTextResponse(
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        status_code=500,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(webhook.router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(orders.router, prefix="/api/v1/stores/{store_id}/orders", tags=["orders"])
app.include_router(products.router, prefix="/api/v1/stores/{store_id}/products", tags=["products"])
app.include_router(batches.router, prefix="/api/v1/stores/{store_id}/batches", tags=["batches"])
