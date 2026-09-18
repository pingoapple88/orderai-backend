"""青泉谷 P1 OrderAI 隔離 UAT 的合成基準、清理與唯讀驗證。

此模組永不由 FastAPI 啟動事件呼叫。只有明確執行 scripts/p1_uat_seed.py
且所有 UAT 防護條件成立時，才會寫入最小合成 company／store／owner／product。
絕不建立 Customer、Order、BillingRecord、LINE webhook event 或正式交易資料。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AIExtraction,
    AIUsageLog,
    AttachmentDraft,
    AuditLog,
    BillingRecord,
    Company,
    Customer,
    ErpDeliveryOutbox,
    IntakeConversation,
    InventoryInquiry,
    LineWebhookEvent,
    Order,
    OrderBatch,
    Plan,
    Product,
    Store,
    User,
    UserPreference,
)

settings = get_settings()

_UAT_ENVIRONMENT = "uat"
_UAT_MARKER = "qingquan-p1-uat"
_SYNTHETIC_COMPANY_NAME = "青泉谷 P1 UAT 合成公司"
_SYNTHETIC_PLAN_NAME = "qingquan-p1-uat"
_SYNTHETIC_STORE_KEY = "qingquan-p1-uat-orderai-store"
_SYNTHETIC_STORE_NAME = "青泉谷 P1 UAT 合成店"
_SYNTHETIC_OWNER_LINE_ID = "UAT_QINGQUAN_P1_ORDERAI_OWNER"
_SYNTHETIC_OWNER_EMAIL = "qingquan-p1-orderai-owner@uat.invalid"
_SYNTHETIC_PRODUCT_NAME = "青泉谷 P1 UAT 合成商品"
_SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL = "p1_uat_direct"


class P1UatSeedBlocked(RuntimeError):
    """任一 UAT 條件不成立即拒絕寫入或清理。"""


@dataclass(frozen=True)
class P1UatSeedResult:
    company_id: int
    store_id: int
    owner_user_id: int
    product_id: int
    created: bool

    def safe_summary(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "store_id": self.store_id,
            "owner_user_id": self.owner_user_id,
            "product_id": self.product_id,
            "created": self.created,
            "synthetic_only": True,
            "formal_customer_created": False,
            "formal_order_created": False,
            "payment_created": False,
            "line_webhook_event_created": False,
        }


def _assert_uat_database_target() -> None:
    """以 UAT marker、顯式開關與精準內網 host 三重限制種子操作。"""
    if settings.environment.strip().lower() != _UAT_ENVIRONMENT:
        raise P1UatSeedBlocked("P1_UAT_ENVIRONMENT_NOT_ALLOWED")
    if settings.p1_uat_environment_marker != _UAT_MARKER:
        raise P1UatSeedBlocked("P1_UAT_MARKER_INVALID")
    if not settings.p1_uat_seed_enabled:
        raise P1UatSeedBlocked("P1_UAT_SEED_DISABLED")
    configured_host = settings.p1_uat_database_host.strip().lower()
    database_host = (urlsplit(settings.database_url).hostname or "").lower()
    if not configured_host or not database_host or database_host != configured_host:
        raise P1UatSeedBlocked("P1_UAT_DATABASE_HOST_INVALID")
    if not configured_host.endswith(".railway.internal"):
        raise P1UatSeedBlocked("P1_UAT_DATABASE_HOST_NOT_ISOLATED")


def _one(db: Session, statement, error_code: str):
    value = db.execute(statement).scalar_one_or_none()
    if value is None:
        raise P1UatSeedBlocked(error_code)
    return value


def _forbidden_counts(db: Session, store_id: int) -> dict[str, int]:
    """只計數，不回傳敏感資料；所有結果都應維持零。"""
    return {
        "formal_customers": int(db.scalar(select(func.count()).select_from(Customer).where(Customer.store_id == store_id)) or 0),
        "formal_orders": int(db.scalar(select(func.count()).select_from(Order).where(Order.store_id == store_id)) or 0),
        "payment_records": int(db.scalar(select(func.count()).select_from(BillingRecord).where(BillingRecord.store_id == store_id)) or 0),
        "line_webhook_events": int(
            db.scalar(
                select(func.count()).select_from(LineWebhookEvent).where(
                    LineWebhookEvent.store_id == store_id,
                    LineWebhookEvent.channel != _SYNTHETIC_DIRECT_ACCEPTANCE_CHANNEL,
                )
            )
            or 0
        ),
    }


def seed_p1_uat(db: Session) -> P1UatSeedResult:
    """建立或取得最小合成基準；可重跑，不自動建立可送件案例。"""
    _assert_uat_database_target()
    company = db.execute(select(Company).where(Company.name == _SYNTHETIC_COMPANY_NAME)).scalar_one_or_none()
    created = company is None
    if company is None:
        company = Company(name=_SYNTHETIC_COMPANY_NAME)
        db.add(company)
        db.flush()

    plan = db.execute(
        select(Plan).where(Plan.name == _SYNTHETIC_PLAN_NAME, Plan.channel == "direct")
    ).scalar_one_or_none()
    if plan is None:
        plan = Plan(
            name=_SYNTHETIC_PLAN_NAME,
            channel="direct",
            monthly_price=0,
            currency="TWD",
            features={"synthetic_uat_only": True, "p1_intake": True},
        )
        db.add(plan)
        db.flush()

    store = db.execute(select(Store).where(Store.store_key == _SYNTHETIC_STORE_KEY)).scalar_one_or_none()
    if store is None:
        store = Store(
            name=_SYNTHETIC_STORE_NAME,
            market="tw",
            industry_type="ecom",
            company_id=company.id,
            plan="lite",
            store_key=_SYNTHETIC_STORE_KEY,
            line_channel_id=None,
        )
        db.add(store)
        db.flush()
    elif store.company_id != company.id:
        raise P1UatSeedBlocked("P1_UAT_STORE_COMPANY_MISMATCH")

    owner = db.execute(select(User).where(User.line_id == _SYNTHETIC_OWNER_LINE_ID)).scalar_one_or_none()
    if owner is None:
        owner = User(
            email=_SYNTHETIC_OWNER_EMAIL,
            line_id=_SYNTHETIC_OWNER_LINE_ID,
            name="青泉谷 P1 UAT 合成管理者",
            role="owner",
            store_id=store.id,
            plan_id=plan.id,
            is_active=True,
        )
        db.add(owner)
        db.flush()
    elif owner.store_id != store.id or owner.plan_id != plan.id:
        raise P1UatSeedBlocked("P1_UAT_OWNER_SCOPE_MISMATCH")

    product = db.execute(
        select(Product).where(Product.store_id == store.id, Product.name == _SYNTHETIC_PRODUCT_NAME)
    ).scalar_one_or_none()
    if product is None:
        product = Product(
            store_id=store.id,
            name=_SYNTHETIC_PRODUCT_NAME,
            aliases=["P1 UAT 商品"],
            unit="盒",
            price_cents=12300,
            is_active=True,
        )
        db.add(product)
        db.flush()

    baseline = _forbidden_counts(db, store.id)
    if any(baseline.values()):
        raise P1UatSeedBlocked("P1_UAT_BASELINE_NOT_EMPTY")
    if created:
        db.add(AuditLog(
            user_id=owner.id,
            store_id=store.id,
            action="p1.uat_seed.applied",
            resource_type="p1_uat_seed",
            resource_id=store.id,
            new_value={
                "company_id": company.id,
                "synthetic_only": True,
                "formal_customer_created": False,
                "formal_order_created": False,
                "payment_created": False,
                "line_webhook_event_created": False,
            },
        ))
    db.commit()
    return P1UatSeedResult(company.id, store.id, owner.id, product.id, created)


def verify_p1_uat_baseline(db: Session) -> dict[str, Any]:
    """唯讀核對合成基準與禁止副作用；資料異常一律拒絕宣告可測。"""
    _assert_uat_database_target()
    store = _one(db, select(Store).where(Store.store_key == _SYNTHETIC_STORE_KEY), "P1_UAT_STORE_NOT_FOUND")
    company = _one(db, select(Company).where(Company.id == store.company_id, Company.name == _SYNTHETIC_COMPANY_NAME), "P1_UAT_COMPANY_NOT_FOUND")
    owner = _one(db, select(User).where(User.store_id == store.id, User.line_id == _SYNTHETIC_OWNER_LINE_ID), "P1_UAT_OWNER_NOT_FOUND")
    product = _one(db, select(Product).where(Product.store_id == store.id, Product.name == _SYNTHETIC_PRODUCT_NAME, Product.is_active.is_(True)), "P1_UAT_PRODUCT_NOT_FOUND")
    forbidden = _forbidden_counts(db, store.id)
    if any(forbidden.values()):
        raise P1UatSeedBlocked("P1_UAT_FORBIDDEN_SIDE_EFFECT_DETECTED")
    return {
        "company_id": company.id,
        "store_id": store.id,
        "owner_user_id": owner.id,
        "product_id": product.id,
        **forbidden,
        "pending_cases": int(db.scalar(select(func.count()).select_from(IntakeConversation).where(IntakeConversation.store_id == store.id)) or 0),
        "erp_delivery_outbox": int(db.scalar(select(func.count()).select_from(ErpDeliveryOutbox).where(ErpDeliveryOutbox.store_id == store.id)) or 0),
        "synthetic_only": True,
    }


def clear_p1_uat(db: Session) -> None:
    """重置精準識別的合成 UAT 動態資料，保留基礎資產與 append-only 稽核。"""
    _assert_uat_database_target()
    store = _one(db, select(Store).where(Store.store_key == _SYNTHETIC_STORE_KEY), "P1_UAT_STORE_NOT_FOUND")
    if any(_forbidden_counts(db, store.id).values()):
        raise P1UatSeedBlocked("P1_UAT_CLEAR_BLOCKED_BY_FORMAL_SIDE_EFFECT")
    owner = _one(
        db,
        select(User).where(User.store_id == store.id, User.line_id == _SYNTHETIC_OWNER_LINE_ID),
        "P1_UAT_OWNER_NOT_FOUND",
    )
    db.execute(delete(AIUsageLog).where(AIUsageLog.store_id == store.id))
    db.execute(delete(AIExtraction).where(AIExtraction.store_id == store.id))
    db.execute(delete(AttachmentDraft).where(AttachmentDraft.store_id == store.id))
    db.execute(delete(ErpDeliveryOutbox).where(ErpDeliveryOutbox.store_id == store.id))
    db.execute(delete(IntakeConversation).where(IntakeConversation.store_id == store.id))
    db.execute(delete(LineWebhookEvent).where(LineWebhookEvent.store_id == store.id))
    db.execute(delete(InventoryInquiry).where(InventoryInquiry.store_id == store.id))
    db.execute(delete(OrderBatch).where(OrderBatch.store_id == store.id))
    db.add(AuditLog(
        user_id=owner.id,
        store_id=store.id,
        action="p1.uat_cleanup.applied",
        resource_type="p1_uat_pending_reset",
        resource_id=store.id,
        new_value={
            "synthetic_only": True,
            "audit_retained": True,
            "base_assets_retained": True,
            "formal_customer_created": False,
            "formal_order_created": False,
            "payment_created": False,
            "line_webhook_event_created": False,
        },
    ))
    db.commit()
