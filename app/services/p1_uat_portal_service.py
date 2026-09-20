"""青泉谷 P1 staging UAT Portal 的 synthetic-only 操作邊界。

此服務只寫入既有 P1 event ledger 與加密人工覆核草稿。它不建立正式客戶、
訂單、付款、庫存、履約或發票，也不建立 ERP outbox 或呼叫任何外部服務。
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AuditLog,
    Company,
    ErpDeliveryOutbox,
    IntakeConversation,
    InventoryInquiry,
    LineWebhookEvent,
    Product,
    Store,
    User,
)
from app.p1_uat_seed import (
    P1UatSeedBlocked,
    _SYNTHETIC_COMPANY_NAME,
    _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
    _SYNTHETIC_OWNER_LINE_ID,
    _SYNTHETIC_PRODUCT_NAME,
    _SYNTHETIC_STORE_KEY,
    _SYNTHETIC_STORE_NAME,
    _assert_uat_database_target,
    _forbidden_counts,
)
from app.services.p1_intake_service import create_text_case

settings = get_settings()

_PORTAL_EVENT_TYPE = "synthetic_uat_portal"
_PORTAL_EVENT_PREFIX = "p1-uat-portal:"
_PORTAL_REVIEW_REASON = "uat_human_confirmed_pending_only"
_PORTAL_CREATE_REASON = "synthetic_uat_portal_pending_only"


class P1UatPortalBlocked(RuntimeError):
    """Portal guard、synthetic scope 或資料安全條件不成立。"""


class P1UatPortalNotFound(RuntimeError):
    """指定 UUID 不屬於 portal synthetic store。"""


class P1UatPortalConflict(RuntimeError):
    """指定案例不再是可維持 pending 的安全人工覆核狀態。"""


def assert_portal_access(access_code: Optional[str]) -> None:
    """所有 JSON action 共用的 fail-closed staging 與 constant-time code 守門。"""
    expected = settings.p1_uat_portal_access_code
    code_matches = secrets.compare_digest(access_code or "", expected or "")
    allowed = (
        settings.p1_uat_portal_enabled
        and settings.p1_uat_portal_environment.strip().lower() == "staging"
        and settings.railway_environment_name.strip().lower() == "staging"
        and bool(expected)
        and bool(access_code)
        and code_matches
    )
    if not allowed:
        raise P1UatPortalBlocked("P1_UAT_PORTAL_ACCESS_DENIED")


def _one(db: Session, statement, error_code: str):
    value = db.execute(statement).scalar_one_or_none()
    if value is None:
        raise P1UatPortalBlocked(error_code)
    return value


def _synthetic_scope(db: Session) -> tuple[Company, Store, User, Product]:
    """重用既有 DB guard，並精準驗證 synthetic company/store/owner/product。"""
    try:
        _assert_uat_database_target()
    except P1UatSeedBlocked as exc:
        raise P1UatPortalBlocked("P1_UAT_PORTAL_DATABASE_SCOPE_INVALID") from exc

    store = _one(
        db,
        select(Store).where(
            Store.store_key == _SYNTHETIC_STORE_KEY,
            Store.name == _SYNTHETIC_STORE_NAME,
            Store.line_channel_id.is_(None),
        ),
        "P1_UAT_PORTAL_STORE_SCOPE_INVALID",
    )
    company = _one(
        db,
        select(Company).where(
            Company.id == store.company_id,
            Company.name == _SYNTHETIC_COMPANY_NAME,
        ),
        "P1_UAT_PORTAL_COMPANY_SCOPE_INVALID",
    )
    owner = _one(
        db,
        select(User).where(
            User.store_id == store.id,
            User.line_id == _SYNTHETIC_OWNER_LINE_ID,
            User.role == "owner",
            User.is_active.is_(True),
        ),
        "P1_UAT_PORTAL_OWNER_SCOPE_INVALID",
    )
    product = _one(
        db,
        select(Product).where(
            Product.store_id == store.id,
            Product.name == _SYNTHETIC_PRODUCT_NAME,
            Product.is_active.is_(True),
        ),
        "P1_UAT_PORTAL_PRODUCT_SCOPE_INVALID",
    )
    if any(_forbidden_counts(db, store.id).values()):
        raise P1UatPortalBlocked("P1_UAT_PORTAL_FORMAL_SIDE_EFFECT_DETECTED")
    inventory_count = int(
        db.scalar(
            select(func.count()).select_from(InventoryInquiry).where(
                InventoryInquiry.store_id == store.id
            )
        )
        or 0
    )
    if inventory_count:
        raise P1UatPortalBlocked("P1_UAT_PORTAL_INVENTORY_SIDE_EFFECT_DETECTED")
    return company, store, owner, product


def _event_id(case_ref: str) -> str:
    try:
        normalized = str(UUID(case_ref))
    except (TypeError, ValueError, AttributeError) as exc:
        raise P1UatPortalNotFound() from exc
    return f"{_PORTAL_EVENT_PREFIX}{normalized}"


def _case_ref(event: LineWebhookEvent) -> str:
    if not event.webhook_event_id.startswith(_PORTAL_EVENT_PREFIX):
        raise P1UatPortalBlocked("P1_UAT_PORTAL_EVENT_SCOPE_INVALID")
    return str(UUID(event.webhook_event_id.removeprefix(_PORTAL_EVENT_PREFIX)))


def _portal_case(
    db: Session,
    *,
    store: Store,
    case_ref: str,
    for_update: bool = False,
) -> tuple[LineWebhookEvent, IntakeConversation]:
    event = db.execute(
        select(LineWebhookEvent).where(
            LineWebhookEvent.company_id == store.company_id,
            LineWebhookEvent.store_id == store.id,
            LineWebhookEvent.channel == _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
            LineWebhookEvent.event_type == _PORTAL_EVENT_TYPE,
            LineWebhookEvent.webhook_event_id == _event_id(case_ref),
        )
    ).scalar_one_or_none()
    if event is None:
        raise P1UatPortalNotFound()
    statement = select(IntakeConversation).where(
        IntakeConversation.company_id == store.company_id,
        IntakeConversation.store_id == store.id,
        IntakeConversation.source_event_id == event.id,
    )
    if for_update:
        statement = statement.with_for_update()
    case = db.execute(statement).scalar_one_or_none()
    if case is None:
        raise P1UatPortalNotFound()
    return event, case


def create_pending_case(
    db: Session,
    *,
    buyer_alias: str,
    product_name: str,
    quantity: int,
    requested_for: str,
    special_requirement: str,
) -> dict[str, Any]:
    """建立 synthetic ledger 與加密草稿；固定 pending，絕不產生 ERP outbox。"""
    company, store, owner, product = _synthetic_scope(db)
    case_uuid = uuid4()
    event_identifier = f"{_PORTAL_EVENT_PREFIX}{case_uuid}"
    now = datetime.now(timezone.utc)
    event = LineWebhookEvent(
        company_id=company.id,
        store_id=store.id,
        channel=_SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
        webhook_event_id=event_identifier,
        event_type=_PORTAL_EVENT_TYPE,
        message_type="text",
        message_id_hmac=hashlib.sha256(event_identifier.encode("utf-8")).hexdigest(),
        source_user_hmac=hashlib.sha256(
            f"synthetic-portal-source:{case_uuid}".encode("utf-8")
        ).hexdigest(),
        occurred_at=now,
        status="processed",
        processed_at=now,
    )
    db.add(event)
    db.flush()
    event_hash = hashlib.sha256(event_identifier.encode("utf-8")).hexdigest()
    db.add(
        AuditLog(
            user_id=owner.id,
            store_id=store.id,
            action="p1.uat_portal.event_recorded",
            resource_type="line_webhook_event",
            resource_id=event.id,
            new_value={
                "company_id": company.id,
                "event_id_sha256": event_hash,
                "channel": _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
                "status": "processed",
                "synthetic_only": True,
            },
        )
    )

    source_text = json.dumps(
        {
            "buyer_alias": buyer_alias,
            "product_name": product_name,
            "quantity": quantity,
            "requested_for": requested_for,
            "special_requirement": special_requirement,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result = SimpleNamespace(
        customer_name=buyer_alias,
        customer_phone=None,
        confidence_score=1.0,
        provider_name="synthetic_uat_portal",
        raw={
            "requested_for": requested_for,
            "special_request": special_requirement,
        },
        items=[
            SimpleNamespace(
                product_name=product_name,
                quantity=quantity,
                unit=product.unit if product_name == product.name else "個",
                evidence="synthetic_uat_portal_form",
            )
        ],
    )
    case = create_text_case(
        db,
        store=store,
        source_event=event,
        source_text=source_text,
        source_user_id=None,
        result=result,
        decision_status="needs_human_review",
        decision_reasons=[_PORTAL_CREATE_REASON],
    )
    outbox_count = int(
        db.scalar(
            select(func.count()).select_from(ErpDeliveryOutbox).where(
                ErpDeliveryOutbox.store_id == store.id,
                ErpDeliveryOutbox.company_id == company.id,
                ErpDeliveryOutbox.conversation_id == case.id,
            )
        )
        or 0
    )
    if case.state != "needs_human_review" or outbox_count:
        raise P1UatPortalBlocked("P1_UAT_PORTAL_PENDING_ONLY_INVARIANT_FAILED")
    if any(_forbidden_counts(db, store.id).values()):
        raise P1UatPortalBlocked("P1_UAT_PORTAL_FORMAL_SIDE_EFFECT_DETECTED")
    return {
        "caseRef": str(case_uuid),
        "eventIdSha256": event_hash,
        "state": case.state,
        "stateVersion": case.state_version,
        "draftEncrypted": bool(case.draft_ciphertext),
        "syntheticOnly": True,
        "erpOutboxCreated": False,
        "formalSideEffectsCreated": False,
    }


def confirm_pending_review(db: Session, *, case_ref: str) -> dict[str, Any]:
    """記錄人工查看；案例仍維持 needs_human_review，且不建立/排入 outbox。"""
    company, store, owner, _product = _synthetic_scope(db)
    event, case = _portal_case(db, store=store, case_ref=case_ref, for_update=True)
    if case.state != "needs_human_review":
        raise P1UatPortalConflict()
    outbox = db.execute(
        select(ErpDeliveryOutbox).where(
            ErpDeliveryOutbox.company_id == company.id,
            ErpDeliveryOutbox.store_id == store.id,
            ErpDeliveryOutbox.conversation_id == case.id,
        )
    ).scalar_one_or_none()
    if outbox is not None:
        raise P1UatPortalBlocked("P1_UAT_PORTAL_OUTBOX_FORBIDDEN")

    codes = list((case.reason_codes or {}).get("codes") or [])
    changed = _PORTAL_REVIEW_REASON not in codes
    if changed:
        codes.append(_PORTAL_REVIEW_REASON)
        case.reason_codes = {"codes": sorted(set(codes))}
        case.state_version += 1
        case.updated_at = datetime.now(timezone.utc)
        db.add(
            AuditLog(
                user_id=owner.id,
                store_id=store.id,
                action="p1.uat_portal.reviewed_pending",
                resource_type="p1_intake_conversation",
                resource_id=case.id,
                new_value={
                    "company_id": company.id,
                    "event_id_sha256": hashlib.sha256(
                        event.webhook_event_id.encode("utf-8")
                    ).hexdigest(),
                    "from_state": "needs_human_review",
                    "to_state": "needs_human_review",
                    "state_version": case.state_version,
                    "synthetic_only": True,
                    "erp_dispatch_attempted": False,
                    "formal_side_effects_created": False,
                },
            )
        )
        db.commit()
        db.refresh(case)
    return {
        "caseRef": _case_ref(event),
        "state": case.state,
        "stateVersion": case.state_version,
        "reviewedPendingOnly": True,
        "alreadyReviewed": not changed,
        "erpDispatchAttempted": False,
        "formalSideEffectsCreated": False,
    }


def portal_status(db: Session) -> dict[str, Any]:
    """回傳聚合與 UUID 狀態；不解密、不回傳來源文字或身分資料。"""
    company, store, _owner, _product = _synthetic_scope(db)
    rows = list(
        db.execute(
            select(LineWebhookEvent, IntakeConversation)
            .join(
                IntakeConversation,
                IntakeConversation.source_event_id == LineWebhookEvent.id,
            )
            .where(
                LineWebhookEvent.company_id == company.id,
                LineWebhookEvent.store_id == store.id,
                LineWebhookEvent.channel == _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
                LineWebhookEvent.event_type == _PORTAL_EVENT_TYPE,
                IntakeConversation.company_id == company.id,
                IntakeConversation.store_id == store.id,
            )
            .order_by(LineWebhookEvent.id.desc())
        ).all()
    )
    cases = []
    reviewed_count = 0
    draft_count = 0
    for event, case in rows:
        codes = set((case.reason_codes or {}).get("codes") or [])
        reviewed = _PORTAL_REVIEW_REASON in codes
        reviewed_count += int(reviewed)
        draft_count += int(bool(case.draft_ciphertext))
        cases.append(
            {
                "caseRef": _case_ref(event),
                "state": case.state,
                "stateVersion": case.state_version,
                "reviewedPendingOnly": reviewed,
            }
        )

    forbidden = _forbidden_counts(db, store.id)
    inventory_count = int(
        db.scalar(
            select(func.count()).select_from(InventoryInquiry).where(
                InventoryInquiry.store_id == store.id
            )
        )
        or 0
    )
    outbox_count = int(
        db.scalar(
            select(func.count()).select_from(ErpDeliveryOutbox).where(
                ErpDeliveryOutbox.company_id == company.id,
                ErpDeliveryOutbox.store_id == store.id,
            )
        )
        or 0
    )
    dispatch_attempt_count = int(
        db.scalar(
            select(func.coalesce(func.sum(ErpDeliveryOutbox.attempt_count), 0)).where(
                ErpDeliveryOutbox.company_id == company.id,
                ErpDeliveryOutbox.store_id == store.id,
            )
        )
        or 0
    )
    return {
        "marker": "STAGING SYNTHETIC ONLY",
        "syntheticOnly": True,
        "eventLedgerCount": len(rows),
        "pendingCaseCount": sum(case.state == "needs_human_review" for _, case in rows),
        "encryptedDraftCount": draft_count,
        "reviewedPendingCount": reviewed_count,
        "erpOutboxCount": outbox_count,
        "erpDispatchAttemptCount": dispatch_attempt_count,
        "formalCustomerCount": forbidden["formal_customers"],
        "formalOrderCount": forbidden["formal_orders"],
        "paymentRecordCount": forbidden["payment_records"],
        "inventoryRecordCount": inventory_count,
        "fulfillmentRecordCount": 0,
        "invoiceRecordCount": 0,
        "cases": cases,
    }


def cleanup_portal(db: Session) -> dict[str, Any]:
    """只刪除 portal 自身動態資料，保留基礎資產、其他 UAT 資料與 audit。"""
    company, store, owner, _product = _synthetic_scope(db)
    event_ids = list(
        db.execute(
            select(LineWebhookEvent.id).where(
                LineWebhookEvent.company_id == company.id,
                LineWebhookEvent.store_id == store.id,
                LineWebhookEvent.channel == _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
                LineWebhookEvent.event_type == _PORTAL_EVENT_TYPE,
            )
        ).scalars()
    )
    case_ids = list(
        db.execute(
            select(IntakeConversation.id).where(
                IntakeConversation.company_id == company.id,
                IntakeConversation.store_id == store.id,
                IntakeConversation.source_event_id.in_(event_ids),
            )
        ).scalars()
    ) if event_ids else []
    if case_ids:
        outbox_count = int(
            db.scalar(
                select(func.count()).select_from(ErpDeliveryOutbox).where(
                    ErpDeliveryOutbox.company_id == company.id,
                    ErpDeliveryOutbox.store_id == store.id,
                    ErpDeliveryOutbox.conversation_id.in_(case_ids),
                )
            )
            or 0
        )
        if outbox_count:
            raise P1UatPortalBlocked("P1_UAT_PORTAL_CLEANUP_OUTBOX_FORBIDDEN")
        db.execute(
            delete(IntakeConversation).where(
                IntakeConversation.company_id == company.id,
                IntakeConversation.store_id == store.id,
                IntakeConversation.id.in_(case_ids),
            )
        )
    if event_ids:
        db.execute(
            delete(LineWebhookEvent).where(
                LineWebhookEvent.company_id == company.id,
                LineWebhookEvent.store_id == store.id,
                LineWebhookEvent.id.in_(event_ids),
            )
        )
    db.add(
        AuditLog(
            user_id=owner.id,
            store_id=store.id,
            action="p1.uat_portal.cleanup",
            resource_type="p1_uat_portal",
            resource_id=store.id,
            new_value={
                "company_id": company.id,
                "synthetic_only": True,
                "deleted_event_count": len(event_ids),
                "deleted_case_count": len(case_ids),
                "audit_retained": True,
                "formal_side_effects_created": False,
            },
        )
    )
    db.commit()
    return {
        "cleared": True,
        "syntheticOnly": True,
        "eventLedgerCount": 0,
        "pendingCaseCount": 0,
        "encryptedDraftCount": 0,
        "auditRetained": True,
        "formalSideEffectsCreated": False,
    }
