"""統一回應格式（API 契約 v1.0 §四）。

成功：{ "success": true,  "data": {...} }（分頁時外加 "pagination"）
失敗：{ "success": false, "error": { "code": "...", "message": "..." } }
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi.responses import JSONResponse


def success_response(data: Any, pagination: Optional[dict] = None) -> dict:
    r: dict = {"success": True, "data": data}
    if pagination is not None:
        r["pagination"] = pagination
    return r


def error_response(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": code, "message": message}},
    )
