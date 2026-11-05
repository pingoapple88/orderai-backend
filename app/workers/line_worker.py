"""LINE Webhook Worker（WO-002：AI 抄單接通）：pre-filter → LLM 解析 → 建單寫 DB → 回覆。

設計邊界：
- v0 一人一店（快照 §九）：order 歸屬 settings.default_store_id，user_id = 該店 owner。
  找不到 store 或 owner → fail-closed（不建孤兒單、不建到錯店）。多店路由見 WO-007。
- 去重：orders.line_event_id UNIQUE。直接 INSERT，撞則 IntegrityError 攔（⛔ 不 check-then-write）。
- 價格只取店家型錄；未命中商品不猜價，轉人工覆核。
- WO-L3-003：圖片（data URL → extract_order(image_url)）、語音（STT → 文字流程）同一建單流程；
  取媒體／轉寫失敗或信心不足 → needs_review，不建單。
- 信心、型錄、數量與原文證據任一未通過 → fail-closed（不建單，只通知）。
- LLM/LINE HTTP、DB 需真環境；沙箱以注入 db + mock provider 驗邏輯層。
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import httpx

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Customer, Store, User
from app.services import order_risk_service, order_service, p1_intake_service, product_service, reply_composer

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_text_from_event(event: Dict[str, Any]) -> Optional[str]:
    """從 LINE event 取出文字訊息；非文字訊息回 None（pre-filter）。"""
    msg = event.get("message", {})
    if msg.get("type") == "text":
        return msg.get("text")
    return None


async def _reply(notif, llm, *, user_id: Optional[str], reply_token: Optional[str], outcome: str, **facts) -> None:
    """WO-L3-001：回覆走 reply_composer；組字與送出失敗皆不可阻斷建單（只 log）。"""
    if not (reply_token and user_id):
        return
    text = await reply_composer.compose(outcome, llm=llm, **facts)
    try:
        await notif.send_message(to=user_id, text=text, reply_token=reply_token)
    except Exception:  # noqa: BLE001 — 訂單／audit 已先寫入，回覆失敗不回滾
        logger.warning("LINE reply failed outcome=%s", outcome)


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


IMAGE_EXTRACT_HINT = "（買家傳來一張訂購圖片：只抽取圖片中清楚可見的商品與數量，看不清楚不要猜。）"


def _audit_fail_closed(db: Session, *, principal: dict, reason_code: str, source_text: str) -> None:
    order_risk_service.audit_ai_decision(
        db,
        principal=principal,
        extraction=None,
        decision=order_risk_service.RiskDecision(
            status="needs_review",
            reasons=[reason_code],
            threshold=settings.ai_confidence_threshold,
        ),
        source_text=source_text,
    )


async def _resolve_input(
    event: Dict[str, Any], *, content, stt,
) -> Tuple[Optional[str], Optional[str], str, Optional[Tuple[str, str]]]:
    """WO-L3-003：把 text／image／audio 統一成 (text, image_url, source_text, fail)。

    fail = (reason_code, outcome)；非 None 時不得呼叫 LLM、不得建單。
    圖片：IMessageContentProvider 取圖 → data URL 交 extract_order(image_url=…)。
    語音：IMessageContentProvider 取音檔 → ISpeechToTextProvider 轉文字 → 走文字流程；
          轉寫信心不足或無法提供信心 → needs_review（不硬猜）。
    """
    msg = event.get("message") or {}
    msg_type = msg.get("type")
    message_id = str(msg.get("id") or "")
    if msg_type == "text":
        return msg.get("text"), None, msg.get("text") or "", None

    source_text = "line_{}:{}".format(msg_type, message_id)
    try:
        media = await content.get_message_content(message_id)
    except Exception as exc:  # noqa: BLE001 — 取媒體失敗一律 fail-closed
        reason = getattr(exc, "reason_code", None) or "media_fetch_failed"
        logger.warning("media fetch failed type=%s reason=%s", msg_type, reason)
        return None, None, source_text, (reason, reply_composer.OUTCOME_PROVIDER_ERROR)

    if msg_type == "image":
        if not media.content_type.startswith("image/"):
            return None, None, source_text, ("media_type_mismatch", reply_composer.OUTCOME_NEEDS_REVIEW)
        data_url = "data:{};base64,{}".format(media.content_type, base64.b64encode(media.data).decode("ascii"))
        return IMAGE_EXTRACT_HINT, data_url, source_text, None

    # audio
    try:
        tr = await stt.transcribe(
            media.data, content_type=media.content_type or "audio/m4a", language=settings.stt_language,
        )
    except Exception as exc:  # noqa: BLE001 — STT 失敗／未設定 → 轉人工
        reason = getattr(exc, "reason_code", None) or "stt_error"
        logger.warning("stt failed reason=%s", reason)
        return None, None, source_text, (reason, reply_composer.OUTCOME_NEEDS_REVIEW)
    transcript = (tr.text or "").strip()
    if not transcript:
        return None, None, source_text, ("stt_empty_transcript", reply_composer.OUTCOME_NEEDS_REVIEW)
    if tr.confidence is None:
        return None, None, transcript, ("stt_confidence_unavailable", reply_composer.OUTCOME_NEEDS_REVIEW)
    if tr.confidence < settings.stt_min_confidence:
        return None, None, transcript, ("stt_confidence_below_threshold", reply_composer.OUTCOME_NEEDS_REVIEW)
    return transcript, None, transcript, None


async def _process_one_event(db: Session, event: Dict[str, Any], llm, notif, *, content=None, stt=None) -> None:
    reply_token: Optional[str] = event.get("replyToken")
    source = event.get("source", {})
    user_id: Optional[str] = source.get("userId")
    line_event_id: Optional[str] = event.get("webhookEventId")

    if settings.p1_intake_enabled:
        await _process_p1_event(db, event, llm, notif)
        return

    # pre-filter：文字、（啟用時）圖片與語音；其餘略過
    msg_type = (event.get("message") or {}).get("type") if event.get("type") == "message" else None
    allowed = {"text"}
    if settings.line_image_intake_enabled:
        allowed.add("image")
    if settings.line_audio_intake_enabled:
        allowed.add("audio")
    if msg_type not in allowed or (msg_type == "text" and not _get_text_from_event(event)):
        logger.debug("skip event type=%s message=%s", event.get("type"), msg_type)
        return

    # v0 一人一店：解析歸屬 store + owner（fail-closed）
    store, owner = _resolve_store_owner(db, settings.default_store_id)
    if store is None or owner is None:
        return

    industry_type = store.industry_type or "ecom"

    principal = {"user_id": owner.id, "store_id": store.id}

    if msg_type != "text":
        from app.providers import get_message_content_provider, get_speech_to_text_provider
        content = content or get_message_content_provider()
        if msg_type == "audio":
            stt = stt or get_speech_to_text_provider()
    text, image_url, source_text, fail = await _resolve_input(event, content=content, stt=stt)
    if fail is not None:
        reason_code, outcome = fail
        _audit_fail_closed(db, principal=principal, reason_code=reason_code, source_text=source_text)
        await _reply(
            notif, llm, user_id=user_id, reply_token=reply_token, outcome=outcome, reason_code=reason_code,
        )
        return

    # LLM 解析（價格一律不採用模型輸出，下方以型錄帶價）
    try:
        result = await llm.extract_order(text=text, image_url=image_url, industry_type=industry_type)
    except Exception as exc:  # noqa: BLE001 — 對外服務失敗一律降級通知
        logger.error("LLM extract_order failed: %s", exc)
        reason_code = getattr(exc, "reason_code", None)
        if reason_code is None:
            reason_code = "provider_timeout" if isinstance(
                exc, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError)
            ) else "provider_error"
        _audit_fail_closed(db, principal=principal, reason_code=reason_code, source_text=source_text)
        # reason_code 已寫 audit；不對客人顯示技術碼。
        await _reply(
            notif, llm, user_id=user_id, reply_token=reply_token,
            outcome=reply_composer.OUTCOME_PROVIDER_ERROR, reason_code=reason_code,
        )
        return

    logger.info(
        "ai_extraction confidence=%.2f industry=%s items=%d",
        result.confidence_score, result.industry_type, len(result.items),
    )

    # 只以店家型錄帶價，不相信模型提供的價格。
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
        source_text=source_text,
    )
    if decision.status != "approved":
        logger.warning(
            "order extraction requires review: reasons=%s confidence=%.2f",
            decision.reasons,
            result.confidence_score,
        )
        await _reply(
            notif, llm, user_id=user_id, reply_token=reply_token,
            outcome=reply_composer.OUTCOME_NEEDS_REVIEW,
            reason_code=",".join(decision.reasons) or None,
        )
        return

    # 只有完成所有防禦檢查後才建立客戶資料與訂單。
    customer = _get_or_create_customer(db, store.id, user_id, result.customer_name)

    # 建單：單價來自型錄，去重靠 line_event_id UNIQUE。
    base_extraction = result.raw or {
        "confidence_score": result.confidence_score,
        "industry_type": result.industry_type,
    }
    data = {
        "items": [
            {"product_name": p["product_name"], "quantity": p["quantity"],
             "unit_price": int(p["unit_price_cents"])}
            for p in priced
        ],
        "customer_id": customer.id if customer else None,
        "customer_name": result.customer_name,
        "customer_phone": result.customer_phone,
        "channel": "line",
        "line_event_id": line_event_id,
        # 帶價快照：每行 matchedProductId / unitPriceCents（未命中皆 null），供前端與稽核。
        "ai_extraction": {
            **base_extraction,
            "lines": [
                {"productName": p["product_name"], "quantity": p["quantity"],
                 "matchedProductId": p["matched_product_id"],
                 "unitPriceCents": p["unit_price_cents"]}
                for p in priced
            ],
        },
    }
    try:
        order = order_service.create_order(db, principal, data)
    except IntegrityError:
        db.rollback()
        logger.info("duplicate line_event_id=%s，skip（已建過單）", line_event_id)
        return

    # 回覆買家：事實區塊只用型錄帶價結果與 DB 訂單總計（整數分）。
    await _reply(
        notif, llm, user_id=user_id, reply_token=reply_token,
        outcome=reply_composer.OUTCOME_ORDER_CREATED,
        items=[
            reply_composer.ReplyItem(
                name=p["product_name"], qty=int(p["quantity"]),
                unit_price_cents=int(p["unit_price_cents"]),
            )
            for p in priced
        ],
        total_cents=int(order.total_cents),
    )


async def _safe_attachment_followup(notif, *, reply_token: Optional[str], user_id: Optional[str]) -> None:
    """未配置官方 Messaging channel 時不假裝可對客補問。"""
    if not (
        settings.p1_attachment_followup_enabled
        and settings.line_messaging_access_token
        and reply_token
        and user_id
    ):
        return
    try:
        await notif.send_message(
            to=user_id,
            reply_token=reply_token,
            text="已收到附件。為避免辨識錯誤，請直接以文字提供訂購人、商品、數量、需要時間與特別要求。",
        )
    except Exception:  # noqa: BLE001 - 通知不可用時保留人工覆核案例，不重試外部呼叫。
        logger.warning("P1 attachment follow-up unavailable; retained for human review")


async def _process_p1_event(db: Session, event: Dict[str, Any], llm, notif) -> None:
    """P1：只建立受控草稿／blocked outbox，絕不建立本地一般 Order 或 Customer。"""
    line_event_id = event.get("webhookEventId")
    if not isinstance(line_event_id, str) or not line_event_id:
        return
    try:
        store = p1_intake_service.resolve_p1_store(db)
    except p1_intake_service.P1IntakeConfigurationError as exc:
        logger.error("P1 intake store scope unavailable: %s", exc)
        return
    source_event = p1_intake_service.claim_event(db, store_id=store.id, webhook_event_id=line_event_id)
    if source_event is None:
        return

    message = event.get("message") or {}
    message_type = message.get("type")
    source = event.get("source") or {}
    source_user_id = source.get("userId")
    reply_token = event.get("replyToken")
    try:
        if message_type in {"image", "audio", "file"}:
            p1_intake_service.create_attachment_case(
                db, store=store, source_event=source_event, media_type=message_type
            )
            await _safe_attachment_followup(notif, reply_token=reply_token, user_id=source_user_id)
            p1_intake_service.finish_event(db, source_event)
            return

        text = _get_text_from_event(event)
        if not text:
            # 非訂單文字、貼圖、位置等事件也不會變成訂單。
            p1_intake_service.create_text_case(
                db,
                store=store,
                source_event=source_event,
                source_text="",
                source_user_id=source_user_id,
                result=type("EmptyExtraction", (), {"items": [], "customer_name": None, "customer_phone": None, "confidence_score": 0.0, "provider_name": "", "raw": {}})(),
                decision_status="needs_review",
                decision_reasons=["unsupported_message_type"],
            )
            p1_intake_service.finish_event(db, source_event)
            return

        try:
            result = await llm.extract_order(text=text, industry_type=store.industry_type or "ecom")
        except Exception as exc:  # noqa: BLE001 - 外部解析失敗只建立人工覆核草稿。
            reason = getattr(exc, "reason_code", None) or (
                "provider_timeout" if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError)) else "provider_error"
            )
            p1_intake_service.create_text_case(
                db,
                store=store,
                source_event=source_event,
                source_text=text,
                source_user_id=source_user_id,
                result=type("EmptyExtraction", (), {"items": [], "customer_name": None, "customer_phone": None, "confidence_score": 0.0, "provider_name": "", "raw": {}})(),
                decision_status="needs_review",
                decision_reasons=[reason],
            )
            p1_intake_service.finish_event(db, source_event)
            return

        priced = product_service.price_extracted_items(db, store.id, result.items)
        decision = order_risk_service.evaluate_order_extraction(
            db,
            extraction=result,
            priced_items=priced,
            default_threshold=settings.ai_confidence_threshold,
        )
        p1_intake_service.create_text_case(
            db,
            store=store,
            source_event=source_event,
            source_text=text,
            source_user_id=source_user_id,
            result=result,
            decision_status=decision.status,
            decision_reasons=decision.reasons,
        )
        p1_intake_service.finish_event(db, source_event)
    except p1_intake_service.P1IntakeConfigurationError as exc:
        db.rollback()
        source_event = db.get(type(source_event), source_event.id)
        if source_event is not None:
            p1_intake_service.finish_event(db, source_event, error_code=str(exc))
        logger.error("P1 intake failed closed: %s", exc)
    except Exception:
        db.rollback()
        source_event = db.get(type(source_event), source_event.id)
        if source_event is not None:
            p1_intake_service.finish_event(db, source_event, error_code="P1_INTAKE_PROCESSING_FAILED")
        logger.exception("P1 intake processing failed")


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
