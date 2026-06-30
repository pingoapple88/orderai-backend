"""LINE Webhook（情境一）：只入列、立即回 200，不做任何 LLM/DB 重活。"""
from fastapi import APIRouter, Request, Response

from app.providers import get_queue

router = APIRouter()


@router.post("/line")
async def line_webhook(request: Request) -> Response:
    payload = await request.json()
    # 立即入列 → 由 Worker 非同步消化（避免 LINE 5 秒逾時重試雪崩）
    get_queue().enqueue(payload)
    return Response(status_code=200)
