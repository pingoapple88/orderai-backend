"""OrderAI 獨立服務註冊、方案狀態與事件 outbox；所有租戶讀寫皆以 company_id／store_id 範圍限制。"""
from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.merchcore_module import MODULE_KEY, MODULE_VERSION, OrderAIMerchCoreAdapter, normalize_locale
from app.core.config import get_settings
from app.models import AuditLog, Company, ModuleEventOutbox, ModuleRegistration, Plan, Store, User


def _store_key() -> str:
    return "ord_{}".format(uuid4().hex)


def register_self_service(
    db: Session,
    *,
    company_name: str,
    store_name: str,
    channel: str,
    locale: str,
    idempotency_key: str,
    plan_name: str | None = None,
) -> ModuleRegistration:
    """建立待啟用註冊；public request 不可提供 company_id，伺服器自行產生整數租戶鍵。"""
    if channel not in {"direct", "dealer", "enterprise"}:
        raise HTTPException(status_code=422, detail="Unsupported channel")
    existing = db.execute(
        select(ModuleRegistration).where(
            ModuleRegistration.module_key == MODULE_KEY,
            ModuleRegistration.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    if plan_name:
        plan = db.execute(
            select(Plan).where(Plan.name == plan_name, Plan.channel == channel)
        ).scalar_one_or_none()
        if plan is None:
            raise HTTPException(status_code=422, detail="Plan is unavailable for this channel")

    company = Company(name=company_name.strip())
    db.add(company)
    db.flush()
    store = Store(
        name=store_name.strip(),
        company_id=company.id,
        store_key=_store_key(),
        plan=plan_name or "pending_activation",
    )
    db.add(store)
    db.flush()
    normalized_locale = normalize_locale(locale)
    registration = ModuleRegistration(
        company_id=company.id,
        store_id=store.id,
        module_key=MODULE_KEY,
        module_version=MODULE_VERSION,
        channel=channel,
        locale=normalized_locale,
        status="pending_activation",
        idempotency_key=idempotency_key,
    )
    db.add(registration)
    db.flush()

    event_type = get_settings().module_registration_event_type.strip()
    allowed_event_types = {
        item.strip() for item in get_settings().module_event_types.split(",") if item.strip()
    }
    if not event_type or event_type not in allowed_event_types:
        raise RuntimeError("MODULE_REGISTRATION_EVENT_TYPE is not approved by registry")
    event = OrderAIMerchCoreAdapter.build_event(
        event_type=event_type,
        company_id=company.id,
        idempotency_key=idempotency_key,
        payload={
            "module_key": MODULE_KEY,
            "module_version": MODULE_VERSION,
            "store_key": store.store_key,
            "channel": channel,
            "locale": normalized_locale,
            "plan_name": plan_name,
            "status": registration.status,
        },
        signing_secret=get_settings().module_event_signing_secret,
    )
    registration.event_id = event["event_id"]
    db.add(
        ModuleEventOutbox(
            event_id=event["event_id"],
            event_version=event["event_version"],
            event_type=event["event_type"],
            occurred_at=event["occurred_at"],
            company_id=company.id,
            idempotency_key=idempotency_key,
            payload=event["payload"],
            signature=event["signature"],
            status="pending",
        )
    )
    db.add(
        AuditLog(
            store_id=store.id,
            action="module.registration.requested",
            resource_type="module_registration",
            resource_id=registration.id,
            new_value={
                "module_key": MODULE_KEY,
                "module_version": MODULE_VERSION,
                "company_id": company.id,
                "channel": channel,
                "locale": normalized_locale,
                "plan_name": plan_name,
                "status": registration.status,
                "event_id": event["event_id"],
            },
        )
    )
    db.commit()
    db.refresh(registration)
    return registration


def list_plans(db: Session, *, channel: str) -> list[Plan]:
    if channel not in {"direct", "dealer", "enterprise"}:
        raise HTTPException(status_code=422, detail="Unsupported channel")
    return db.execute(
        select(Plan).where(Plan.channel == channel).order_by(Plan.monthly_price.asc(), Plan.id.asc())
    ).scalars().all()


def get_module_status(db: Session, *, principal: dict) -> dict:
    """以 JWT 的 store_id 推導 company_id，不接受 client 提供的租戶值。"""
    store_id = principal.get("store_id")
    user = db.get(User, principal.get("user_id"))
    if user is None or user.store_id != store_id:
        raise HTTPException(status_code=403, detail="Tenant scope denied")
    store = db.get(Store, store_id)
    if store is None or store.company_id is None:
        raise HTTPException(status_code=404, detail="Module tenant not found")
    registration = db.execute(
        select(ModuleRegistration)
        .where(
            ModuleRegistration.store_id == store.id,
            ModuleRegistration.company_id == store.company_id,
            ModuleRegistration.module_key == MODULE_KEY,
        )
        .order_by(ModuleRegistration.id.desc())
    ).scalars().first()
    plan = None
    if store.plan:
        channel = registration.channel if registration else "direct"
        plan = db.execute(
            select(Plan)
            .where(Plan.name == store.plan, Plan.channel == channel)
            .order_by(Plan.id.asc())
        ).scalars().first()
    return {
        "company_id": store.company_id,
        "store_key": store.store_key,
        "registration": registration,
        "plan_name": store.plan,
        "channel": registration.channel if registration else None,
        "ai_usage_count": user.ai_usage_count if user else 0,
        "ai_extraction_limit": plan.ai_extraction_limit if plan else None,
        "status": registration.status if registration else "not_registered",
    }
