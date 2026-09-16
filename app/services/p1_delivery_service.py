"""青泉谷 P1 的人工覆核與隔離 ERP 送件邊界。

此服務不由 webhook 或 worker 自動觸發。只有具店鋪範圍 JWT 的人員先完成
客戶文字確認與人工覆核，且顯式開啟 localhost 隔離開關後，才能透過可替換
ERP Adapter 送出「待確認客戶／待確認訂單」。流程不建立本地正式訂單、客戶、
付款、庫存預留、扣庫、出貨或開票。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import providers
from app.core.config import get_settings
from app.core.events import event_bus
from app.core.interfaces.erp_ingest import ErpIngestBlockedError, IErpIngestProvider
from app.models import AuditLog, ErpDeliveryOutbox, IntakeConversation, Store
from app.services.p1_intake_service import build_erp_requests_from_outbox

settings = get_settings()


class P1ConversationNotFound(Exception):
    """案例不屬於已驗證的店鋪／公司範圍。"""


class P1StateConflict(Exception):
    """案例或 outbox 已處於不可重複的狀態。"""


class P1DeliveryBlocked(Exception):
    """隔離送件開關、主機或待確認資料不符合要求。"""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _company_id(db: Session, store_id: int) -> int:
    store = db.get(Store, store_id)
    if store is None or store.company_id is None:
        raise PermissionError("tenant company_id unresolved; fail-closed")
    return store.company_id


def _case(db: Session, store_id: int, company_id: int, conversation_id: int) -> Optional[IntakeConversation]:
    return db.execute(
        select(IntakeConversation)
        .join(Store, Store.id == IntakeConversation.store_id)
        .where(
            IntakeConversation.id == conversation_id,
            IntakeConversation.store_id == store_id,
            Store.company_id == company_id,
        )
    ).scalar_one_or_none()


def _outbox(db: Session, store_id: int, company_id: int, conversation_id: int) -> Optional[ErpDeliveryOutbox]:
    return db.execute(
        select(ErpDeliveryOutbox)
        .where(
            ErpDeliveryOutbox.conversation_id == conversation_id,
            ErpDeliveryOutbox.store_id == store_id,
            ErpDeliveryOutbox.company_id == company_id,
        )
    ).scalar_one_or_none()


def _audit(db: Session, principal: dict, store_id: int, action: str, resource_id: int, details: dict) -> None:
    """只記錄狀態、ID、錯誤碼；不得放入解密草稿、電話或 LINE 身分。"""
    db.add(AuditLog(
        user_id=principal.get("user_id"),
        store_id=store_id,
        action=action,
        resource_type="p1_intake_conversation",
        resource_id=resource_id,
        old_value=None,
        new_value=details,
    ))


def list_cases(db: Session, store_id: int, state: Optional[str] = None) -> list[IntakeConversation]:
    company_id = _company_id(db, store_id)
    stmt = (
        select(IntakeConversation)
        .join(Store, Store.id == IntakeConversation.store_id)
        .where(IntakeConversation.store_id == store_id, Store.company_id == company_id)
        .order_by(IntakeConversation.created_at.desc())
    )
    if state is not None:
        if state not in {"needs_human_review", "awaiting_customer_confirmation", "awaiting_erp_delivery", "closed"}:
            raise ValueError("invalid P1 case state")
        stmt = stmt.where(IntakeConversation.state == state)
    return list(db.execute(stmt).scalars())


def review_case(
    db: Session,
    principal: dict,
    store_id: int,
    conversation_id: int,
    *,
    customer_confirmed: bool,
    note: Optional[str] = None,
) -> IntakeConversation:
    """人工覆核案例；客戶未確認時不得排入 ERP outbox。"""
    company_id = _company_id(db, store_id)
    case = _case(db, store_id, company_id, conversation_id)
    if case is None:
        raise P1ConversationNotFound()
    if case.state not in {"needs_human_review", "awaiting_customer_confirmation"}:
        raise P1StateConflict("P1 case is not reviewable")

    outbox = _outbox(db, store_id, company_id, conversation_id)
    old_state = case.state
    if not customer_confirmed:
        case.state = "awaiting_customer_confirmation"
        action = "p1.intake.awaiting_customer_confirmation"
    else:
        if outbox is None:
            raise P1DeliveryBlocked("P1_CASE_NOT_DELIVERABLE")
        if outbox.status != "blocked":
            raise P1StateConflict("P1 outbox is not blocked")
        case.state = "awaiting_erp_delivery"
        outbox.status = "queued"
        outbox.last_error_code = None
        action = "p1.intake.review_approved"
    case.state_version += 1
    case.updated_at = datetime.now(timezone.utc)
    _audit(
        db, principal, store_id, action, case.id,
        {
            "company_id": company_id,
            "from_state": old_state,
            "to_state": case.state,
            "customer_confirmed": customer_confirmed,
            "note_recorded": bool(note),
            "outbox_queued": bool(customer_confirmed and outbox is not None),
            "reservation_created": False,
            "payment_created": False,
        },
    )
    db.commit()
    db.refresh(case)
    event_bus.publish(
        "p1.intake_case.reviewed",
        {"conversation_id": case.id, "store_id": store_id, "company_id": company_id, "state": case.state},
    )
    return case


def _assert_isolated_target() -> None:
    """完全以設定 fail-closed；即使 Adapter 存在也不得跨出隔離 allowlist。"""
    if not settings.p1_isolated_delivery_enabled:
        raise P1DeliveryBlocked("P1_ISOLATED_DELIVERY_DISABLED")
    parsed = urlsplit(settings.p1_erp_base_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise P1DeliveryBlocked("P1_ERP_BASE_URL_INVALID")
    if hostname not in settings.p1_erp_isolated_allowed_host_set:
        raise P1DeliveryBlocked("P1_ERP_TARGET_NOT_ISOLATED")


async def dispatch_outbox(
    db: Session,
    principal: dict,
    store_id: int,
    conversation_id: int,
    *,
    provider: Optional[IErpIngestProvider] = None,
) -> ErpDeliveryOutbox:
    """人工觸發的一次性隔離送件；不輪詢，重送沿用資料庫冪等鍵。"""
    _assert_isolated_target()
    company_id = _company_id(db, store_id)
    case = _case(db, store_id, company_id, conversation_id)
    if case is None:
        raise P1ConversationNotFound()
    if case.state != "awaiting_erp_delivery":
        raise P1StateConflict("P1 case is not approved for ERP delivery")
    outbox = _outbox(db, store_id, company_id, conversation_id)
    if outbox is None or outbox.status not in {"queued", "failed"}:
        raise P1StateConflict("P1 outbox is not dispatchable")

    provider = provider or providers.get_erp_ingest_provider()
    customer_request, order_request = build_erp_requests_from_outbox(outbox)
    try:
        customer_result = await provider.create_pending_customer(customer_request)
        if customer_result.status != "accepted":
            raise ErpIngestBlockedError("ERP_PENDING_CUSTOMER_REJECTED")
        try:
            pending_customer_id = int(customer_result.reference)
        except (TypeError, ValueError) as exc:
            raise ErpIngestBlockedError("ERP_PENDING_CUSTOMER_REFERENCE_INVALID") from exc
        order_result = await provider.submit_pending_confirmation_order(
            replace(order_request, pending_customer_id=pending_customer_id)
        )
        if order_result.status != "accepted":
            raise ErpIngestBlockedError("ERP_PENDING_ORDER_REJECTED")
    except ErpIngestBlockedError as exc:
        outbox.attempt_count += 1
        outbox.status = "failed"
        outbox.last_error_code = exc.reason_code
        _audit(
            db, principal, store_id, "p1.erp_outbox.failed", case.id,
            {"company_id": company_id, "error_code": exc.reason_code, "attempt_count": outbox.attempt_count},
        )
        db.commit()
        raise P1DeliveryBlocked(exc.reason_code) from exc

    outbox.attempt_count += 1
    outbox.status = "delivered"
    outbox.last_error_code = None
    case.state = "closed"
    case.state_version += 1
    case.updated_at = datetime.now(timezone.utc)
    _audit(
        db, principal, store_id, "p1.erp_outbox.delivered", case.id,
        {
            "company_id": company_id,
            "provider": customer_result.provider,
            "pending_customer_reference": customer_result.reference,
            "pending_order_reference": order_result.reference,
            "reservation_created": False,
            "payment_created": False,
        },
    )
    db.commit()
    db.refresh(outbox)
    event_bus.publish(
        "p1.erp_outbox.delivered",
        {"conversation_id": case.id, "store_id": store_id, "company_id": company_id, "outbox_id": outbox.id},
    )
    return outbox
