"""LINE Webhook Worker：redact → ILLMProvider → risk gate → audit → 受控建單。

Queue 僅送入去識別化 envelope；provider 失敗可依 queue adapter 有限重試，
超限後進入 dead-letter，絕不因背景例外自動建立訂單。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any, Dict, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Customer, Store, User
from app.services import order_risk_service, order_service, product_service
from app.services.pii_redaction import redact_pii
from app.services.queue_payload import with_retry_attempt

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(frozen=True)
class WorkerEventOutcome:
    status: str
    reason_code: Optional[str] = None
    retryable: bool = False


def _get_text_from_event(event: Dict[str, Any]) -> Optional[str]:
    """從 LINE event 取出文字訊息；非文字或非字串訊息回 None。"""
    msg = event.get("message", {})
    if not isinstance(msg, dict) or msg.get("type") != "text":
        return None
    text = msg.get("text")
    return text if isinstance(text, str) else None


def _resolve_store_owner(db: Session, store_id: int) -> Tuple[Optional[Store], Optional[User]]:
    """v0 一人一店：找不到 store 或 owner 即 fail-closed。"""
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
    """依 store 與去識別化來源識別值取或建客戶；缺值不建立。"""
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


async def _process_one_event(db: Session, event: Dict[str, Any], llm, notif) -> WorkerEventOutcome:
    reply_token = event.get("replyToken") if isinstance(event.get("replyToken"), str) else None
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    user_id = source.get("userId") or source.get("lineUserHash")
    user_id = user_id if isinstance(user_id, str) else None
    line_event_id = event.get("webhookEventId") or event.get("lineEventHash")
    line_event_id = line_event_id if isinstance(line_event_id, str) else None

    text = _get_text_from_event(event)
    if not text:
        logger.debug("skip non-text event type=%s", event.get("type"))
        return WorkerEventOutcome("ignored")
    safe_text = redact_pii(text)

    store, owner = _resolve_store_owner(db, settings.default_store_id)
    if store is None or owner is None:
        return WorkerEventOutcome("needs_review", "tenant_scope_unavailable")
    industry_type = store.industry_type or "ecom"
    principal = {"user_id": owner.id, "store_id": store.id}

    try:
        result = await llm.extract_order(text=safe_text, industry_type=industry_type)
    except Exception as exc:  # noqa: BLE001 — 外部 provider 失敗一律 fail-closed
        logger.error("LLM extract_order failed: %s", exc)
        reason_code = getattr(exc, "reason_code", None)
        if reason_code is None:
            reason_code = "provider_timeout" if isinstance(
                exc, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError)
            ) else "provider_error"
        order_risk_service.audit_ai_decision(
            db,
            principal=principal,
            extraction=None,
            decision=order_risk_service.RiskDecision(
                status="needs_review",
                reasons=[reason_code],
                threshold=settings.ai_confidence_threshold,
            ),
            source_text=safe_text,
        )
        if reply_token and user_id:
            await notif.send_message(
                to=user_id,
                text="此筆內容需人工確認（原因：{}）。".format(reason_code),
                reply_token=reply_token,
            )
        return WorkerEventOutcome("needs_review", reason_code, retryable=True)

    logger.info(
        "ai_extraction confidence=%.2f industry=%s items=%d",
        result.confidence_score, result.industry_type, len(result.items),
    )
    priced = product_service.price_extracted_items(db, store.id, result.items)
    decision = order_risk_service.evaluate_order_extraction(
        db,
        extraction=result,
        priced_items=priced,
        default_threshold=settings.ai_confidence_threshold,
    )
    order_risk_service.audit_ai_decision(
        db,
        principal=principal,
        extraction=result,
        decision=decision,
        source_text=safe_text,
    )
    if decision.status != "approved":
        logger.warning(
            "order extraction requires review: reasons=%s confidence=%.2f",
            decision.reasons,
            result.confidence_score,
        )
        if reply_token and user_id:
            await notif.send_message(
                to=user_id,
                text="這筆內容需要人工確認，請補充商品名稱與數量，或請店家協助確認。",
                reply_token=reply_token,
            )
        reason_code = decision.reasons[0] if decision.reasons else "needs_review"
        return WorkerEventOutcome("needs_review", reason_code)

    customer = _get_or_create_customer(db, store.id, user_id, result.customer_name)
    base_extraction = result.raw or {
        "confidence_score": result.confidence_score,
        "industry_type": result.industry_type,
    }
    data = {
        "items": [
            {"product_name": p["product_name"], "quantity": p["quantity"], "unit_price": p["unit_price_cents"]}
            for p in priced
        ],
        "customer_id": customer.id if customer else None,
        "customer_name": result.customer_name,
        "customer_phone": result.customer_phone,
        "channel": "line",
        "line_event_id": line_event_id,
        "ai_extraction": {
            **base_extraction,
            "lines": [
                {
                    "productName": p["product_name"],
                    "quantity": p["quantity"],
                    "matchedProductId": p["matched_product_id"],
                    "unitPriceCents": p["unit_price_cents"],
                }
                for p in priced
            ],
        },
    }
    try:
        order_service.create_order(db, principal, data)
    except IntegrityError:
        db.rollback()
        logger.info("duplicate line_event_id=%s，skip（已建過單）", line_event_id)
        return WorkerEventOutcome("duplicate")

    if reply_token and user_id:
        item_lines = "\n".join("- {} x{}".format(i.product_name, i.quantity) for i in result.items)
        await notif.send_message(
            to=user_id,
            text="已收到您的訂單：\n{}\n\n請稍候確認。".format(item_lines),
            reply_token=reply_token,
        )
    return WorkerEventOutcome("approved")


async def process_webhook_event(
    payload: Dict[str, Any], db: Optional[Session] = None
) -> list[WorkerEventOutcome]:
    """解析 Queue envelope；每個 event 皆經過同一條 redaction、risk 與 audit 路徑。"""
    from app.providers import get_llm_provider, get_notification_provider

    llm = get_llm_provider()
    notif = get_notification_provider()
    own_session = db is None
    if own_session:
        db = SessionLocal()
    outcomes: list[WorkerEventOutcome] = []
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    try:
        for event in events:
            if isinstance(event, dict):
                outcomes.append(await _process_one_event(db, event, llm, notif))
    finally:
        if own_session:
            db.close()
    return outcomes


def _queue_attempt(payload: Dict[str, Any]) -> int:
    events = payload.get("events")
    if not isinstance(events, list) or not events or not isinstance(events[0], dict):
        return 0
    metadata = events[0].get("queueMeta")
    attempt = metadata.get("attempt") if isinstance(metadata, dict) else 0
    return attempt if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt >= 0 else 0


def route_retryable_outcomes(payload: Dict[str, Any], outcomes: list[WorkerEventOutcome], queue) -> None:
    """依 Queue abstraction 處理有限重試；超限僅進入人工覆核 dead-letter。"""
    current_attempt = _queue_attempt(payload)
    maximum_attempts = max(0, settings.queue_max_retries)
    for outcome in outcomes:
        if not outcome.retryable:
            continue
        next_payload = with_retry_attempt(payload, current_attempt + 1)
        if current_attempt < maximum_attempts:
            queue.enqueue_retry(next_payload)
        else:
            queue.dead_letter(next_payload, reason_code=outcome.reason_code or "provider_error")


def run_worker(payload: Dict[str, Any]) -> None:
    """同步 Queue 入口：Provider 失敗才經過有限重試，其他 outcome 不自動重送。"""
    from app.providers import get_queue

    outcomes = asyncio.run(process_webhook_event(payload))
    route_retryable_outcomes(payload, outcomes, get_queue())


def run_dead_letter(payload: Dict[str, Any]) -> None:
    """dead-letter 消費端只留下人工確認訊號，絕不建立訂單。"""
    logger.warning("line webhook moved to dead-letter reason=%s", payload.get("reason_code"))
