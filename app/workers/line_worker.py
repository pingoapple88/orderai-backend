"""LINE Webhook Worker（WO-002：AI 抄單接通）：pre-filter → LLM 解析 → 建單寫 DB → 回覆。

設計邊界：
- v0 一人一店（快照 §九）：order 歸屬 settings.default_store_id，user_id = 該店 owner。
  找不到 store 或 owner → fail-closed（不建孤兒單、不建到錯店）。多店路由見 WO-007。
- 去重：orders.line_event_id UNIQUE。直接 INSERT，撞則 IntegrityError 攔（⛔ 不 check-then-write）。
- 價格 option A：v0 不自動算價，unit_price 留 0（team-mom 事後 PUT 補價），⛔ 無 ×100。
- confidence < threshold → fail-closed（不建單，只通知）。
- LLM/LINE HTTP、DB 需真環境；沙箱以注入 db + mock provider 驗邏輯層。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Customer, Store, User
from app.services import order_service

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_text_from_event(event: Dict[str, Any]) -> Optional[str]:
    """從 LINE event 取出文字訊息；非文字訊息回 None（pre-filter）。"""
    msg = event.get("message", {})
    if msg.get("type") == "text":
        return msg.get("text")
    return None


def _resolve_store_owner(db: Session, store_id: int) -> Tuple[Optional[Store], Optional[User]]:
    """v0 一人一店：驗證 store 存在 + 取該店 owner。任一缺 → (None, None) fail-closed。"""
    if not store_id:
        logger.warning("default_store_id 未設定（=0），fail-closed，不建單")
        return None, None
    store = db.get(Store, store_id)
    if store is None:
        logger.warning("store_id=%s 不存在，fail-closed，不建單", store_id)
        return None, None
    owner = db.execute(
        select(User).where(User.store_id == store_id, User.role == "owner")
    ).scalars().first()
    if owner is None:
        logger.warning("store_id=%s 無 owner，fail-closed，不建單", store_id)
        return None, None
    return store, owner


def _get_or_create_customer(
    db: Session, store_id: int, line_user_id: Optional[str], name: Optional[str]
) -> Optional[Customer]:
    """依 (store_id, line_user_id) 取或建 customer；無 line_user_id 則不綁（回 None）。
    customer 綁定 race 無害（最多重複一筆），故此處 check-then-create；
    嚴格去重僅施於 order 的 line_event_id。"""
    if not line_user_id:
        return None
    cust = db.execute(
        select(Customer).where(
            Customer.store_id == store_id, Customer.line_user_id == line_user_id
        )
    ).scalars().first()
    if cust is not None:
        return cust
    cust = Customer(store_id=store_id, line_user_id=line_user_id, name=name or "LINE 客戶")
    db.add(cust)
    db.flush()
    return cust


async def _process_one_event(db: Session, event: Dict[str, Any], llm, notif) -> None:
    reply_token: Optional[str] = event.get("replyToken")
    source = event.get("source", {})
    user_id: Optional[str] = source.get("userId")
    line_event_id: Optional[str] = event.get("webhookEventId")

    # pre-filter：只處理文字訊息
    text = _get_text_from_event(event)
    if not text:
        logger.debug("skip non-text event type=%s", event.get("type"))
        return

    # v0 一人一店：解析歸屬 store + owner（fail-closed）
    store, owner = _resolve_store_owner(db, settings.default_store_id)
    if store is None or owner is None:
        return

    industry_type = store.industry_type or "ecom"

    # LLM 解析
    try:
        result = await llm.extract_order(text=text, industry_type=industry_type)
    except Exception as exc:  # noqa: BLE001 — 對外服務失敗一律降級通知
        logger.error("LLM extract_order failed: %s", exc)
        if reply_token and user_id:
            await notif.send_message(
                to=user_id, text="系統忙碌中，請稍後再試。", reply_token=reply_token
            )
        return

    logger.info(
        "ai_extraction confidence=%.2f industry=%s items=%d",
        result.confidence_score, result.industry_type, len(result.items),
    )

    # fail-closed：信心不足不建單
    if result.confidence_score < settings.ai_confidence_threshold:
        logger.warning(
            "confidence %.2f < threshold %.2f, skip order creation",
            result.confidence_score, settings.ai_confidence_threshold,
        )
        if reply_token and user_id:
            await notif.send_message(
                to=user_id,
                text="無法解析訂單內容，請重新傳送清楚的訂單截圖或文字。",
                reply_token=reply_token,
            )
        return

    # 綁下單客戶（依 LINE userId）
    customer = _get_or_create_customer(db, store.id, user_id, result.customer_name)

    # 建單（v0 單價 0；去重靠 line_event_id UNIQUE，撞則 IntegrityError）
    principal = {"user_id": owner.id, "store_id": store.id}
    data = {
        "items": [
            {"product_name": it.product_name, "quantity": it.quantity,
             "unit_price": it.unit_price}  # v0 = 0，⛔ 無 ×100
            for it in result.items
        ],
        "customer_id": customer.id if customer else None,
        "customer_name": result.customer_name,
        "customer_phone": result.customer_phone,
        "channel": "line",
        "line_event_id": line_event_id,
        "ai_extraction": result.raw or {
            "confidence_score": result.confidence_score,
            "industry_type": result.industry_type,
        },
    }
    try:
        order_service.create_order(db, principal, data)
    except IntegrityError:
        db.rollback()
        logger.info("duplicate line_event_id=%s，skip（已建過單）", line_event_id)
        return

    # 回覆買家
    if reply_token and user_id:
        item_lines = "\n".join(
            "- {} x{}".format(i.product_name, i.quantity) for i in result.items
        )
        reply_text = "已收到您的訂單：\n{}\n\n請稍候確認。".format(item_lines)
        await notif.send_message(to=user_id, text=reply_text, reply_token=reply_token)


async def process_webhook_event(payload: Dict[str, Any], db: Optional[Session] = None) -> None:
    """Worker 主流程：解析一個 LINE Webhook payload。
    db 可注入（測試傳真 test session）；否則自開 SessionLocal（正式 RQ 路徑）。"""
    from app.providers import get_llm_provider, get_notification_provider

    llm = get_llm_provider()
    notif = get_notification_provider()

    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        for event in payload.get("events", []):
            await _process_one_event(db, event, llm, notif)
    finally:
        if own_session:
            db.close()


def run_worker(payload: Dict[str, Any]) -> None:
    """同步入口（供 RQ worker 呼叫）：RQ 不 await 協程，故此處用 asyncio.run 執行 async body。"""
    asyncio.run(process_webhook_event(payload))
