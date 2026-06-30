"""LINE Webhook Worker（PR-3 任務四）：pre-filter → LLM 解析 → 扣額度 → 建單 → 回覆。

誠實邊界：
- LLM HTTP、LINE HTTP、DB 需真環境，沙箱只驗 import/邏輯層
- confidence < threshold 時 fail-closed（不建單，只通知）
- 所有 AI 決策寫入 ai_usage_logs（律八）
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_text_from_event(event: Dict[str, Any]) -> Optional[str]:
    """從 LINE event 取出文字訊息；非文字訊息回 None（pre-filter）。"""
    msg = event.get("message", {})
    if msg.get("type") == "text":
        return msg.get("text")
    return None


async def process_webhook_event(payload: Dict[str, Any]) -> None:
    """Worker 主流程：解析一個 LINE Webhook payload。"""
    from app.providers import get_llm_provider, get_notification_provider

    llm = get_llm_provider()
    notif = get_notification_provider()

    events = payload.get("events", [])
    for event in events:
        reply_token: Optional[str] = event.get("replyToken")
        source = event.get("source", {})
        user_id: Optional[str] = source.get("userId")

        # pre-filter：只處理文字訊息
        text = _get_text_from_event(event)
        if not text:
            logger.debug("skip non-text event type=%s", event.get("type"))
            continue

        # TODO(PR-4)：從 DB 查詢 tenant 的 industry_type 與 ai_usage 額度
        # 目前以預設值 ecom 執行，soft limit 檢查留給 PR-4 補齊
        industry_type = "ecom"

        # LLM 解析
        try:
            result = await llm.extract_order(text=text, industry_type=industry_type)
        except Exception as exc:
            logger.error("LLM extract_order failed: %s", exc)
            if reply_token and user_id:
                await notif.send_message(
                    to=user_id,
                    text="系統忙碌中，請稍後再試。",
                    reply_token=reply_token,
                )
            continue

        # 律八：AI 決策寫 log（TODO PR-4 補 DB 寫入）
        logger.info(
            "ai_extraction confidence=%.2f industry=%s items=%d",
            result.confidence_score,
            result.industry_type,
            len(result.items),
        )

        # fail-closed：信心不足時不建單
        if result.confidence_score < settings.ai_confidence_threshold:
            logger.warning(
                "confidence %.2f < threshold %.2f, skip order creation",
                result.confidence_score,
                settings.ai_confidence_threshold,
            )
            if reply_token and user_id:
                await notif.send_message(
                    to=user_id,
                    text="無法解析訂單內容，請重新傳送清楚的訂單截圖或文字。",
                    reply_token=reply_token,
                )
            continue

        # TODO(PR-4)：建單寫入 DB（orders + order_items）
        logger.info("order ready to create: %s items", len(result.items))

        # 回覆買家
        if reply_token and user_id:
            item_lines = "\n".join(
                "- {} x{}".format(i.product_name, i.quantity)
                for i in result.items
            )
            reply_text = "已收到您的訂單：\n{}\n\n請稍候確認。".format(item_lines)
            await notif.send_message(
                to=user_id,
                text=reply_text,
                reply_token=reply_token,
            )


def run_worker(payload: Dict[str, Any]) -> None:
    """同步入口（供 RQ worker 呼叫）。"""
    asyncio.run(process_webhook_event(payload))
