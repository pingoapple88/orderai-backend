"""青泉谷 P1 隔離 UAT 的單次 OrderAI→ERP 真實 HMAC 驗收。

本模組只供明確手動執行，完整走既有 text case、人工覆核與 dispatch 狀態機。
它不註冊 LINE webhook、不傳送 LINE 訊息、不建立 OrderAI 正式客戶／訂單／付款，
也不呼叫 ERP 的人工 confirm，因此 ERP 僅能產生待確認客戶與待確認訂單。
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BillingRecord, Customer, ErpDeliveryOutbox, IntakeConversation, LineWebhookEvent, Order, Product, Store, User
from app.p1_uat_seed import (
    P1UatSeedBlocked,
    _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
    _SYNTHETIC_OWNER_LINE_ID,
    _SYNTHETIC_STORE_KEY,
    _assert_uat_database_target,
    _forbidden_counts,
    seed_p1_uat,
)
from app.services.p1_delivery_service import P1DeliveryBlocked, P1StateConflict, dispatch_outbox, review_case
from app.services.p1_intake_service import create_text_case

settings = get_settings()

_UAT_EVENT_ID = "qingquan-p1-uat-direct-e2e-v1"
_UAT_SOURCE_USER_ID = "UAT_QINGQUAN_P1_DIRECT_BUYER"
_UAT_SOURCE_TEXT = "青泉谷 P1 UAT 合成：請訂兩盒，指定 UTC 時間取貨；無其他要求。"
_UAT_REQUESTED_FOR = "2030-01-15T02:00:00+00:00"
_RESUMABLE_CASE_STATE_VERSION = 2


class P1UatAcceptanceBlocked(RuntimeError):
    """隔離條件、基準或既有驗收狀態不符合時，一律停止。"""


@dataclass(frozen=True)
class P1UatAcceptanceResult:
    company_id: int
    store_id: int
    conversation_id: int
    outbox_id: int
    outbox_status: str
    replay_blocked: bool
    reused: bool
    resumed: bool = False
    replay_dispatch_not_attempted: bool = False

    def safe_summary(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "synthetic_only": True,
            "line_webhook_enabled": False,
            "line_message_sent": False,
            "formal_customer_created": False,
            "formal_order_created": False,
            "payment_created": False,
            "reservation_created": False,
            "shipment_created": False,
            "invoice_created": False,
        }


def _assert_direct_acceptance_target() -> None:
    """除種子三重守門外，要求顯式啟用 P1 intake、外部 UAT 交付與 HTTP provider。"""
    if not settings.p1_uat_direct_acceptance_enabled:
        raise P1UatAcceptanceBlocked("P1_UAT_DIRECT_ACCEPTANCE_DISABLED")
    if not settings.p1_intake_enabled:
        raise P1UatAcceptanceBlocked("P1_UAT_INTAKE_DISABLED")
    if not settings.p1_uat_delivery_enabled:
        raise P1UatAcceptanceBlocked("P1_UAT_DELIVERY_DISABLED")
    if settings.p1_erp_ingest_provider.strip().lower() != "http":
        raise P1UatAcceptanceBlocked("P1_UAT_ERP_PROVIDER_NOT_HTTP")


def _one(db: Session, statement, error_code: str):
    value = db.execute(statement).scalar_one_or_none()
    if value is None:
        raise P1UatAcceptanceBlocked(error_code)
    return value


def _synthetic_store(db: Session) -> Store:
    """唯讀取得受 UAT guard 保護的精確合成店鋪。"""
    _assert_uat_database_target()
    return _one(
        db,
        select(Store).where(Store.store_key == _SYNTHETIC_STORE_KEY),
        "P1_UAT_ACCEPTANCE_STORE_NOT_FOUND",
    )


def _acceptance_artifacts(
    db: Session,
    store: Store,
) -> tuple[Optional[LineWebhookEvent], Optional[IntakeConversation], Optional[ErpDeliveryOutbox]]:
    """只定位固定合成事件；絕不讀取草稿、來源身分或加密 payload。"""
    events = list(db.execute(
        select(LineWebhookEvent).where(
            LineWebhookEvent.store_id == store.id,
            LineWebhookEvent.channel == _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
            LineWebhookEvent.webhook_event_id == _UAT_EVENT_ID,
        )
    ).scalars())
    if len(events) > 1:
        raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_EVENT_NOT_UNIQUE")
    if not events:
        return None, None, None
    event = events[0]
    cases = list(db.execute(
        select(IntakeConversation).where(
            IntakeConversation.store_id == store.id,
            IntakeConversation.source_event_id == event.id,
        )
    ).scalars())
    if len(cases) > 1:
        raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_CASE_NOT_UNIQUE")
    if not cases:
        return event, None, None
    case = cases[0]
    outboxes = list(db.execute(
        select(ErpDeliveryOutbox).where(
            ErpDeliveryOutbox.store_id == store.id,
            ErpDeliveryOutbox.conversation_id == case.id,
        )
    ).scalars())
    if len(outboxes) > 1:
        raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_OUTBOX_NOT_UNIQUE")
    return event, case, outboxes[0] if outboxes else None


def _existing_result(db: Session, store: Store) -> Optional[P1UatAcceptanceResult]:
    event, case, outbox = _acceptance_artifacts(db, store)
    if event is None:
        return None
    if case is None:
        raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_CASE_NOT_FOUND")
    if outbox is None:
        raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_OUTBOX_NOT_FOUND")
    if case.state != "closed" or outbox.status != "delivered" or outbox.attempt_count != 1:
        raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_EXISTING_CASE_NOT_CLOSED")
    return P1UatAcceptanceResult(
        company_id=store.company_id,
        store_id=store.id,
        conversation_id=case.id,
        outbox_id=outbox.id,
        outbox_status=outbox.status,
        replay_blocked=True,
        reused=True,
    )


def _forbidden_status_counts(db: Session, store: Store) -> dict[str, int]:
    """唯讀統計；狀態診斷需回報異常數值，但不能因此放行恢復。"""
    counts = _forbidden_counts(db, store.id)
    return {
        **counts,
        "synthetic_direct_event_count": int(
            db.scalar(
                select(func.count()).select_from(LineWebhookEvent).where(
                    LineWebhookEvent.store_id == store.id,
                    LineWebhookEvent.channel == _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
                )
            )
            or 0
        ),
        "pending_case_count": int(
            db.scalar(
                select(func.count()).select_from(IntakeConversation).where(IntakeConversation.store_id == store.id)
            )
            or 0
        ),
        "erp_delivery_outbox_count": int(
            db.scalar(
                select(func.count()).select_from(ErpDeliveryOutbox).where(ErpDeliveryOutbox.store_id == store.id)
            )
            or 0
        ),
    }


def status_p1_uat_acceptance(db: Session) -> dict[str, Any]:
    """完全唯讀的 UAT 診斷；不得建立種子、呼叫 provider 或提交資料庫。"""
    try:
        store = _synthetic_store(db)
        counts = _forbidden_status_counts(db, store)
        event, case, outbox = _acceptance_artifacts(db, store)
        exact_event = event is not None
        resume_allowed = bool(
            exact_event
            and case is not None
            and outbox is not None
            and event.event_type == "synthetic_direct_acceptance"
            and event.message_type == "text"
            and event.status == "processed"
            and case.state == "awaiting_erp_delivery"
            and case.state_version == _RESUMABLE_CASE_STATE_VERSION
            and outbox.status == "queued"
            and outbox.attempt_count == 0
            and outbox.last_error_code is None
            and counts["synthetic_direct_event_count"] == 1
            and counts["pending_case_count"] == 1
            and counts["erp_delivery_outbox_count"] == 1
            and counts["formal_customers"] == 0
            and counts["formal_orders"] == 0
            and counts["payment_records"] == 0
            and counts["line_webhook_events"] == 0
        )
        return {
            "company_id": store.company_id,
            "store_id": store.id,
            "exact_synthetic_event_found": exact_event,
            "case_state": case.state if case else None,
            "case_state_version": case.state_version if case else None,
            "outbox_status": outbox.status if outbox else None,
            "outbox_attempt_count": outbox.attempt_count if outbox else None,
            "outbox_last_error_code": outbox.last_error_code if outbox else None,
            "resume_queued_no_attempt_allowed": resume_allowed,
            "synthetic_only": True,
            **counts,
        }
    except P1UatSeedBlocked as exc:
        raise P1UatAcceptanceBlocked(str(exc)) from exc


def _assert_resume_preconditions(db: Session) -> tuple[Store, IntakeConversation, ErpDeliveryOutbox, int]:
    """恢復僅接受一次未嘗試的精確中斷案例；其他狀態一律拒絕。"""
    _assert_direct_acceptance_target()
    status = status_p1_uat_acceptance(db)
    if not status["resume_queued_no_attempt_allowed"]:
        raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_RESUME_NOT_ALLOWED")
    store = _synthetic_store(db)
    event, case, outbox = _acceptance_artifacts(db, store)
    if event is None or case is None or outbox is None:
        raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_RESUME_NOT_ALLOWED")
    owner = _one(
        db,
        select(User).where(
            User.store_id == store.id,
            User.line_id == _SYNTHETIC_OWNER_LINE_ID,
            User.role == "owner",
            User.is_active.is_(True),
        ),
        "P1_UAT_ACCEPTANCE_OWNER_NOT_FOUND",
    )
    return store, case, outbox, owner.id


async def resume_p1_uat_queued_no_attempt_async(db: Session) -> P1UatAcceptanceResult:
    """單次恢復既有 queued outbox；不重建事件、不覆核、不改 payload，也不自動重試。"""
    try:
        store, case, outbox, owner_id = _assert_resume_preconditions(db)
        try:
            delivered = await dispatch_outbox(db, {"user_id": owner_id}, store.id, case.id)
        except P1DeliveryBlocked as exc:
            raise P1UatAcceptanceBlocked(exc.reason_code) from exc
        except P1StateConflict as exc:
            raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_RESUME_STATE_CONFLICT") from exc
        if delivered.id != outbox.id or delivered.status != "delivered" or delivered.attempt_count != 1:
            raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_RESUME_RESULT_INVALID")
        refreshed_case = db.get(IntakeConversation, case.id)
        if refreshed_case is None or refreshed_case.state != "closed":
            raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_RESUME_CASE_NOT_CLOSED")
        _assert_zero_formal_side_effects(db, store.id)
        return P1UatAcceptanceResult(
            company_id=store.company_id,
            store_id=store.id,
            conversation_id=case.id,
            outbox_id=delivered.id,
            outbox_status=delivered.status,
            replay_blocked=False,
            reused=False,
            resumed=True,
            replay_dispatch_not_attempted=True,
        )
    except P1UatSeedBlocked as exc:
        raise P1UatAcceptanceBlocked(str(exc)) from exc


def resume_p1_uat_queued_no_attempt(db: Session) -> P1UatAcceptanceResult:
    """同步 CLI 包裝；每次呼叫最多進行一次既有 outbox 交付。"""
    return asyncio.run(resume_p1_uat_queued_no_attempt_async(db))


def _assert_zero_formal_side_effects(db: Session, store_id: int) -> dict[str, int]:
    counts = _forbidden_counts(db, store_id)
    if any(counts[key] for key in ("formal_customers", "formal_orders", "payment_records")):
        raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_FORMAL_SIDE_EFFECT_DETECTED")
    return counts


async def run_p1_uat_acceptance_async(db: Session) -> P1UatAcceptanceResult:
    """執行一次既有狀態機的真實 HMAC 交付；已成功時只讀取既有結果，不重送。"""
    try:
        baseline = seed_p1_uat(db)
        _assert_direct_acceptance_target()
        store = _one(db, select(Store).where(Store.id == baseline.store_id), "P1_UAT_ACCEPTANCE_STORE_NOT_FOUND")
        existing = _existing_result(db, store)
        if existing is not None:
            _assert_zero_formal_side_effects(db, store.id)
            return existing

        status = status_p1_uat_acceptance(db)
        if status["exact_synthetic_event_found"]:
            raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_EXISTING_CASE_NOT_CLOSED")
        if any(
            status[key]
            for key in ("formal_customers", "formal_orders", "payment_records", "line_webhook_events", "pending_case_count", "erp_delivery_outbox_count")
        ):
            raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_BASELINE_NOT_EMPTY")
        owner = _one(db, select(User).where(User.id == baseline.owner_user_id, User.store_id == store.id), "P1_UAT_ACCEPTANCE_OWNER_NOT_FOUND")
        product = _one(db, select(Product).where(Product.id == baseline.product_id, Product.store_id == store.id, Product.is_active.is_(True)), "P1_UAT_ACCEPTANCE_PRODUCT_NOT_FOUND")
        event = LineWebhookEvent(
            company_id=store.company_id,
            store_id=store.id,
            channel=_SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
            webhook_event_id=_UAT_EVENT_ID,
            event_type="synthetic_direct_acceptance",
            message_type="text",
            message_id_hmac=hashlib.sha256(_UAT_EVENT_ID.encode()).hexdigest(),
            source_user_hmac=hashlib.sha256(_UAT_SOURCE_USER_ID.encode()).hexdigest(),
            occurred_at=datetime.now(timezone.utc),
            status="processed",
        )
        db.add(event)
        db.flush()
        result = SimpleNamespace(
            customer_name="青泉谷 P1 UAT 合成訂購人",
            customer_phone=None,
            confidence_score=1.0,
            provider_name="synthetic_uat_direct",
            raw={"requested_for": _UAT_REQUESTED_FOR, "special_request": "無其他要求"},
            items=[SimpleNamespace(product_name=product.name, quantity=2, unit=product.unit, evidence="synthetic_uat_direct")],
        )
        case = create_text_case(
            db,
            store=store,
            source_event=event,
            source_text=_UAT_SOURCE_TEXT,
            source_user_id=_UAT_SOURCE_USER_ID,
            result=result,
            decision_status="approved",
            decision_reasons=[],
        )
        principal = {"user_id": owner.id}
        reviewed = review_case(db, principal, store.id, case.id, customer_confirmed=True, note="synthetic_uat_direct_acceptance")
        if reviewed.state != "awaiting_erp_delivery":
            raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_REVIEW_STATE_INVALID")
        delivered = await dispatch_outbox(db, principal, store.id, case.id)
        replay_blocked = False
        try:
            await dispatch_outbox(db, principal, store.id, case.id)
        except P1StateConflict:
            replay_blocked = True
        if not replay_blocked:
            raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_REPLAY_NOT_BLOCKED")
        _assert_zero_formal_side_effects(db, store.id)
        return P1UatAcceptanceResult(
            company_id=store.company_id,
            store_id=store.id,
            conversation_id=case.id,
            outbox_id=delivered.id,
            outbox_status=delivered.status,
            replay_blocked=True,
            reused=False,
        )
    except P1UatSeedBlocked as exc:
        raise P1UatAcceptanceBlocked(str(exc)) from exc
    except P1DeliveryBlocked as exc:
        raise P1UatAcceptanceBlocked(exc.reason_code) from exc


def run_p1_uat_acceptance(db: Session) -> P1UatAcceptanceResult:
    """同步 CLI 包裝；無既有 event loop 時才可呼叫。"""
    return asyncio.run(run_p1_uat_acceptance_async(db))


def verify_p1_uat_acceptance(db: Session) -> dict[str, Any]:
    """唯讀核對單筆合成交付結果與 OrderAI 端的零正式交易副作用。"""
    _assert_direct_acceptance_target()
    store = _synthetic_store(db)
    result = _existing_result(db, store)
    if result is None:
        raise P1UatAcceptanceBlocked("P1_UAT_ACCEPTANCE_NOT_RUN")
    counts = _assert_zero_formal_side_effects(db, store.id)
    return {
        **result.safe_summary(),
        **counts,
        "synthetic_direct_event_count": int(db.scalar(select(func.count()).select_from(LineWebhookEvent).where(LineWebhookEvent.store_id == store.id, LineWebhookEvent.channel == _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL)) or 0),
        "erp_delivery_outbox_count": int(db.scalar(select(func.count()).select_from(ErpDeliveryOutbox).where(ErpDeliveryOutbox.store_id == store.id)) or 0),
    }
