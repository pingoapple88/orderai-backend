"""LINE Webhook（PR-3 任務三）：HMAC-SHA256 簽章驗證 + 入列。

安全設計：
- 驗章失敗回 401，不入列（fail-closed）
- 使用 verify_line_signature（compare_digest 防時序攻擊）
- channel_secret 從 ENV 讀取，不入 DB
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.core.config import get_settings
from app.core.security import verify_line_signature
from app.providers import get_queue
from app.services.queue_payload import build_line_queue_envelope

router = APIRouter()
settings = get_settings()


@router.post("/line")
async def line_webhook(request: Request) -> Response:
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_line_signature(body, signature, settings.line_messaging_channel_secret):
        return Response(status_code=401)

    # 簽章通過才入列 → Worker 非同步消化（避免 LINE 5 秒逾時重試雪崩）
    import json
    try:
        payload = json.loads(body)
    except Exception:
        return Response(status_code=400)
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        return Response(status_code=400)

    queue = get_queue()
    for event in payload["events"]:
        envelope = build_line_queue_envelope(event)
        if envelope is None:
            continue
        safe_payload, dedupe_key = envelope
        queue.enqueue_unique(safe_payload, dedupe_key=dedupe_key)
    return Response(status_code=200)
