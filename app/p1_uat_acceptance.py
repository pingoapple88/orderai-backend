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
    _forbidden_counts,
    seed_p1_uat,
    verify_p1_uat_baseline,
)
from app.services.p1_delivery_service import P1StateConflict, dispatch_outbox, review_case
from app.services.p1_intake_service import create_text_case

settings = get_settings()

_UAT_EVENT_ID = "qingquan-p1-uat-direct-e2e-v1"
_UAT_SOURCE_USER_ID = "UAT_QINGQUAN_P1_DIRECT_BUYER"
_UAT_SOURCE_TEXT = "青泉谷 P1 UAT 合成：請訂兩盒，指定 UTC 時間取貨；無其他要求。"
_UAT_REQUESTED_FOR = "2030-01-15T02:00:00+00:00"


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


def _existing_result(db: Session, store: Store) -> Optional[P1UatAcceptanceResult]:
    event = db.execute(
        select(LineWebhookEvent).where(
            LineWebhookEvent.store_id == store.id,
            LineWebhookEvent.channel == _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
            LineWebhookEvent.webhook_event_id == _UAT_EVENT_ID,
        )
    ).scalar_one_or_none()
    if event is None:
        return None
    case = _one(
        db,
        select(IntakeConversation).where(IntakeConversation.store_id == store.id, IntakeConversation.source_event_id == event.id),
        "P1_UAT_ACCEPTANCE_CASE_NOT_FOUND",
    )
    outbox = _one(
        db,
        select(ErpDeliveryOutbox).where(ErpDeliveryOutbox.store_id == store.id, ErpDeliveryOutbox.conversation_id == case.id),
        "P1_UAT_ACCEPTANCE_OUTBOX_NOT_FOUND",
    )
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

        verify_p1_uat_baseline(db)
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


def run_p1_uat_acceptance(db: Session) -> P1UatAcceptanceResult:
    """同步 CLI 包裝；無既有 event loop 時才可呼叫。"""
    return asyncio.run(run_p1_uat_acceptance_async(db))


def verify_p1_uat_acceptance(db: Session) -> dict[str, Any]:
    """唯讀核對單筆合成交付結果與 OrderAI 端的零正式交易副作用。"""
    _assert_direct_acceptance_target()
    baseline = seed_p1_uat(db)
    store = _one(db, select(Store).where(Store.id == baseline.store_id), "P1_UAT_ACCEPTANCE_STORE_NOT_FOUND")
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
