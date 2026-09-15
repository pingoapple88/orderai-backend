"""青泉谷 P1：簽章驗證後的事件帳本、受控草稿與 ERP blocked outbox。

本模組不呼叫 LINE 媒體下載 API、不執行 OCR/STT、不連線 ERP；其職責僅為把
驗簽後事件轉成可稽核、可去重、加密保存的待人工確認資料。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.events import event_bus
from app.core.interfaces.erp_ingest import (
    PendingConfirmationOrderItem,
    PendingConfirmationOrderRequest,
    PendingCustomerRequest,
)
from app.models import (
    AttachmentDraft,
    AuditLog,
    ErpDeliveryOutbox,
    IntakeConversation,
    LineWebhookEvent,
    Store,
)

settings = get_settings()


class P1IntakeConfigurationError(RuntimeError):
    """P1 必要安全設定缺漏時的 fail-closed 錯誤。"""


def _hmac_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = settings.p1_identity_hmac_key.strip()
    if not key:
        raise P1IntakeConfigurationError("P1_IDENTITY_HMAC_KEY_MISSING")
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _fernet() -> Fernet:
    key = settings.p1_pii_encryption_key.strip()
    if not key:
        raise P1IntakeConfigurationError("P1_PII_ENCRYPTION_KEY_MISSING")
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise P1IntakeConfigurationError("P1_PII_ENCRYPTION_KEY_INVALID") from exc


def encrypt_draft(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _fernet().encrypt(normalized.encode("utf-8")).decode("utf-8")


def decrypt_draft(ciphertext: str) -> dict[str, Any]:
    try:
        raw = _fernet().decrypt(ciphertext.encode("utf-8"))
        return json.loads(raw.decode("utf-8"))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P1IntakeConfigurationError("P1_DRAFT_DECRYPT_FAILED") from exc


def _occurred_at(event: dict[str, Any]) -> Optional[datetime]:
    value = event.get("timestamp")
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def resolve_p1_store(db: Session) -> Store:
    store_id = settings.default_store_id
    if not store_id:
        raise P1IntakeConfigurationError("P1_DEFAULT_STORE_ID_MISSING")
    store = db.get(Store, store_id)
    if store is None:
        raise P1IntakeConfigurationError("P1_STORE_NOT_FOUND")
    if store.company_id is None:
        raise P1IntakeConfigurationError("P1_COMPANY_SCOPE_MISSING")
    return store


def record_line_events(db: Session, payload: dict[str, Any], store: Store) -> list[int]:
    """驗簽後、入列前寫入最小事件帳本；UNIQUE 撞到代表重送，直接略過。"""
    if store.company_id is None:
        raise P1IntakeConfigurationError("P1_COMPANY_SCOPE_MISSING")
    # P1 一經啟用，即使當次事件沒有可識別欄位，也不能在缺少金鑰的狀態下
    # 部分運作，避免下一個事件降級為明文或不可去重的身分資料。
    _fernet()
    if not settings.p1_identity_hmac_key.strip():
        raise P1IntakeConfigurationError("P1_IDENTITY_HMAC_KEY_MISSING")

    inserted: list[int] = []
    for event in payload.get("events", []):
        event_id = event.get("webhookEventId")
        if not isinstance(event_id, str) or not event_id:
            continue
        message = event.get("message") or {}
        source = event.get("source") or {}
        try:
            with db.begin_nested():
                row = LineWebhookEvent(
                    company_id=store.company_id,
                    store_id=store.id,
                    channel="line",
                    webhook_event_id=event_id,
                    event_type=str(event.get("type") or "unknown"),
                    message_type=message.get("type"),
                    message_id_hmac=_hmac_value(message.get("id")),
                    source_user_hmac=_hmac_value(source.get("userId")),
                    occurred_at=_occurred_at(event),
                    status="queued",
                )
                db.add(row)
                db.flush()
                inserted.append(row.id)
        except IntegrityError:
            # 事件 ID 已存在：LINE 重送或亂序回放，不再重複入列。
            continue
    db.commit()
    return inserted


def claim_event(db: Session, *, store_id: int, webhook_event_id: str) -> Optional[LineWebhookEvent]:
    """鎖住 queued event，避免同一 webhookEventId 被兩個 worker 重複處理。"""
    row = db.execute(
        select(LineWebhookEvent)
        .where(
            LineWebhookEvent.store_id == store_id,
            LineWebhookEvent.channel == "line",
            LineWebhookEvent.webhook_event_id == webhook_event_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if row is None or row.status != "queued":
        return None
    row.status = "processing"
    db.commit()
    return row


def finish_event(db: Session, event: LineWebhookEvent, *, error_code: Optional[str] = None) -> None:
    event.status = "failed" if error_code else "processed"
    event.error_code = error_code
    event.processed_at = datetime.now(timezone.utc)
    db.commit()


def _audit(db: Session, *, store: Store, action: str, resource_type: str, resource_id: Optional[int], details: dict) -> None:
    db.add(
        AuditLog(
            store_id=store.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            new_value={"company_id": store.company_id, **details},
        )
    )


def _new_case(
    db: Session,
    *,
    store: Store,
    source_event: LineWebhookEvent,
    state: str,
    reason_codes: list[str],
    draft_payload: Optional[dict[str, Any]],
) -> IntakeConversation:
    case = IntakeConversation(
        company_id=store.company_id,
        store_id=store.id,
        source_event_id=source_event.id,
        source_kind=source_event.message_type or source_event.event_type,
        source_user_hmac=source_event.source_user_hmac,
        state=state,
        reason_codes={"codes": sorted(set(reason_codes))},
        draft_ciphertext=encrypt_draft(draft_payload) if draft_payload is not None else None,
    )
    db.add(case)
    db.flush()
    return case


def create_attachment_case(
    db: Session,
    *,
    store: Store,
    source_event: LineWebhookEvent,
    media_type: str,
) -> IntakeConversation:
    case = _new_case(
        db,
        store=store,
        source_event=source_event,
        state="needs_human_review",
        reason_codes=["attachment_ocr_stt_not_configured"],
        draft_payload=None,
    )
    db.add(
        AttachmentDraft(
            company_id=store.company_id,
            store_id=store.id,
            conversation_id=case.id,
            message_id_hmac=source_event.message_id_hmac,
            media_type=media_type,
            restricted_reference=f"line-message-hmac:{source_event.message_id_hmac}" if source_event.message_id_hmac else None,
            status="needs_text_confirmation",
        )
    )
    _audit(
        db,
        store=store,
        action="p1.attachment_draft.create",
        resource_type="intake_conversation",
        resource_id=case.id,
        details={"event_id_sha256": hashlib.sha256(source_event.webhook_event_id.encode()).hexdigest(), "media_type": media_type},
    )
    db.commit()
    event_bus.publish(
        "p1.attachment_draft.created",
        {"conversation_id": case.id, "store_id": store.id, "company_id": store.company_id},
    )
    return case


def _draft_payload(
    *,
    source_text: str,
    source_user_id: Optional[str],
    is_internal_relay: bool,
    result: Any,
    requested_for: Optional[str],
    special_request: Optional[str],
) -> dict[str, Any]:
    return {
        "source_text": source_text,
        "uploader_identity": {
            "line_user_id": source_user_id if is_internal_relay else None,
            "role": "internal_relay" if is_internal_relay else None,
        },
        "buyer_identity": {
            "line_user_id": source_user_id if not is_internal_relay else None,
            "identity_status": "verified_line_source" if source_user_id and not is_internal_relay else "unresolved",
            "candidate_name": getattr(result, "customer_name", None),
            "candidate_phone": getattr(result, "customer_phone", None),
        },
        "requested_items": [
            {
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit": item.unit or "個",
                "evidence": item.evidence,
            }
            for item in (getattr(result, "items", None) or [])
        ],
        "requested_for": requested_for,
        "special_request": special_request,
        "ai": {
            "confidence_score": getattr(result, "confidence_score", None),
            "provider": getattr(result, "provider_name", None),
            "raw": getattr(result, "raw", None),
        },
    }


def _required_field_reasons(
    *, source_user_id: Optional[str], is_internal_relay: bool, result: Any, requested_for: Optional[str], raw: dict
) -> list[str]:
    reasons: list[str] = []
    if is_internal_relay or not source_user_id:
        reasons.append("buyer_identity_unresolved")
    if not getattr(result, "items", None):
        reasons.append("missing_requested_item")
    if not requested_for:
        reasons.append("missing_requested_for")
    if "special_request" not in raw and "specialRequest" not in raw:
        reasons.append("missing_special_request")
    return reasons


def create_text_case(
    db: Session,
    *,
    store: Store,
    source_event: LineWebhookEvent,
    source_text: str,
    source_user_id: Optional[str],
    result: Any,
    decision_status: str,
    decision_reasons: list[str],
) -> IntakeConversation:
    raw = getattr(result, "raw", None) or {}
    is_internal_relay = bool(source_user_id and source_user_id in settings.p1_internal_relay_user_ids)
    requested_for = raw.get("requested_for") or raw.get("requestedFor")
    special_request = raw.get("special_request") if "special_request" in raw else raw.get("specialRequest")
    reasons = list(decision_reasons) + _required_field_reasons(
        source_user_id=source_user_id,
        is_internal_relay=is_internal_relay,
        result=result,
        requested_for=requested_for,
        raw=raw,
    )
    deliverable = decision_status == "approved" and not reasons and settings.p1_erp_sales_location_id > 0
    if decision_status == "approved" and settings.p1_erp_sales_location_id <= 0:
        reasons.append("erp_sales_location_unmapped")
    state = "awaiting_erp_delivery" if deliverable else "needs_human_review"
    payload = _draft_payload(
        source_text=source_text,
        source_user_id=source_user_id,
        is_internal_relay=is_internal_relay,
        result=result,
        requested_for=requested_for,
        special_request=special_request,
    )
    case = _new_case(
        db,
        store=store,
        source_event=source_event,
        state=state,
        reason_codes=reasons,
        draft_payload=payload,
    )
    _audit(
        db,
        store=store,
        action="p1.intake.decision",
        resource_type="intake_conversation",
        resource_id=case.id,
        details={
            "event_id_sha256": hashlib.sha256(source_event.webhook_event_id.encode()).hexdigest(),
            "decision": decision_status,
            "reason_codes": sorted(set(reasons)),
            "confidence_score": getattr(result, "confidence_score", None),
        },
    )
    if deliverable:
        customer_request = PendingCustomerRequest(
            company_id=store.company_id,
            store_id=store.id,
            idempotency_key=f"p1-customer:{store.company_id}:{source_event.webhook_event_id}",
            line_user_id=source_user_id,
            display_name=getattr(result, "customer_name", None),
            phone=getattr(result, "customer_phone", None),
            contact_authorized=True,
            source_channel="line",
        )
        order_request = PendingConfirmationOrderRequest(
            company_id=store.company_id,
            store_id=store.id,
            sales_location_id=settings.p1_erp_sales_location_id,
            idempotency_key=f"p1-order:{store.company_id}:{source_event.webhook_event_id}",
            source_event_id=source_event.webhook_event_id,
            buyer_line_user_id=source_user_id,
            buyer_name=getattr(result, "customer_name", None),
            requested_for=requested_for,
            special_request=special_request,
            items=[
                PendingConfirmationOrderItem(
                    product_name=item.product_name,
                    quantity=item.quantity,
                    unit=item.unit or "個",
                    product_id=None,
                )
                for item in (getattr(result, "items", None) or [])
            ],
        )
        db.add(
            ErpDeliveryOutbox(
                company_id=store.company_id,
                store_id=store.id,
                conversation_id=case.id,
                idempotency_key=f"p1-delivery:{store.company_id}:{source_event.webhook_event_id}",
                payload_ciphertext=encrypt_draft(
                    {"pending_customer": asdict(customer_request), "pending_confirmation_order": asdict(order_request)}
                ),
                status="blocked",
                last_error_code="ERP_CONNECTION_BLOCKED",
            )
        )
        _audit(
            db,
            store=store,
            action="p1.erp_outbox.blocked",
            resource_type="intake_conversation",
            resource_id=case.id,
            details={"reason_code": "ERP_CONNECTION_BLOCKED", "delivery_attempted": False},
        )
    db.commit()
    event_bus.publish(
        "p1.intake_case.created",
        {
            "conversation_id": case.id,
            "store_id": store.id,
            "company_id": store.company_id,
            "state": case.state,
        },
    )
    if deliverable:
        event_bus.publish(
            "p1.erp_outbox.blocked",
            {"conversation_id": case.id, "store_id": store.id, "company_id": store.company_id},
        )
    return case


def build_erp_requests_from_outbox(outbox: ErpDeliveryOutbox) -> tuple[PendingCustomerRequest, PendingConfirmationOrderRequest]:
    """供未來 Adapter worker／單元測試使用；不做任何網路呼叫。"""
    data = decrypt_draft(outbox.payload_ciphertext)
    customer = PendingCustomerRequest(**data["pending_customer"])
    order_data = data["pending_confirmation_order"]
    order_data["items"] = [PendingConfirmationOrderItem(**item) for item in order_data["items"]]
    return customer, PendingConfirmationOrderRequest(**order_data)
