"""OrderAI 獨立服務註冊、方案狀態與事件 outbox；所有租戶讀寫皆以 company_id／store_id 範圍限制。"""
from __future__ import annotations

from hashlib import sha256
import unicodedata
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.merchcore_module import MODULE_KEY, MODULE_VERSION, SUPPORTED_LOCALES
from app.models import AuditLog, Company, ModuleRegistration, Plan, Store, User


def _store_key() -> str:
    return "ord_{}".format(uuid4().hex)


def _company_idempotency_key(company_name: str, idempotency_key: str) -> str:
    """以正規化公司名稱命名 idempotency namespace，保留既有欄位長度與唯一限制。"""
    normalized_company = " ".join(unicodedata.normalize("NFKC", company_name).casefold().split())
    return sha256(f"{MODULE_KEY}\x1f{normalized_company}\x1f{idempotency_key}".encode("utf-8")).hexdigest()


def register_self_service(
    db: Session,
    *,
    company_name: str,
    store_name: str,
    channel: str,
    locale: str,
    idempotency_key: str,
    plan_name: str | None = None,
    referral_source: str | None = None,
) -> ModuleRegistration:
    """建立待啟用註冊；服務狀態只在 OrderAI 內保存，不產生生命週期事件。"""
    company_name = company_name.strip()
    store_name = store_name.strip()
    if not company_name or not store_name:
        raise HTTPException(status_code=422, detail="Company and store names cannot be blank")
    if channel not in {"direct", "dealer", "enterprise"}:
        raise HTTPException(status_code=422, detail="Unsupported channel")
    if locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=422, detail="Unsupported locale")
    if channel == "dealer" and not isinstance(referral_source, str):
        raise HTTPException(status_code=422, detail="Dealer referral source is required")
    if channel == "dealer" and not referral_source.strip():
        raise HTTPException(status_code=422, detail="Dealer referral source is required")
    stored_idempotency_key = _company_idempotency_key(company_name, idempotency_key)
    existing = db.execute(
        select(ModuleRegistration).where(
            ModuleRegistration.module_key == MODULE_KEY,
            ModuleRegistration.idempotency_key == stored_idempotency_key,
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

    company = Company(name=company_name)
    db.add(company)
    db.flush()
    store = Store(
        name=store_name,
        company_id=company.id,
        store_key=_store_key(),
        plan=plan_name or "pending_activation",
    )
    db.add(store)
    db.flush()
    registration = ModuleRegistration(
        company_id=company.id,
        store_id=store.id,
        module_key=MODULE_KEY,
        module_version=MODULE_VERSION,
        channel=channel,
        locale=locale,
        status="pending_activation",
        idempotency_key=stored_idempotency_key,
    )
    db.add(registration)
    db.flush()

    db.add(
        AuditLog(
            store_id=store.id,
            action="module.registration.requested",
            resource_type="module_registration",
            resource_id=registration.id,
            new_value={
                "module_key": MODULE_KEY,
                "module_version": MODULE_VERSION,
                "channel": channel,
                "locale": locale,
                "plan_name": plan_name,
                "status": registration.status,
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
        "registration": registration,
        "plan_name": store.plan,
        "channel": registration.channel if registration else None,
        "ai_usage_count": user.ai_usage_count if user else 0,
        "ai_extraction_limit": plan.ai_extraction_limit if plan else None,
        "status": registration.status if registration else "not_registered",
    }
