"""OrderAI self-service subscription lifecycle, scoped by server-derived principal.

Payment and invoice integrations are injected adapters.  The service never treats an
unknown external status as entitlement activation and never accepts a client scope.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.interfaces.invoice_provider import IInvoiceProvider, InvoiceRequest
from app.core.interfaces.payment_provider import IPaymentProvider, PaymentRequest
from app.core.interfaces.subscription_provider import ISubscriptionProvider, SubscriptionIntent
from app.core.config import get_settings
from app.models import AuditLog, BillingRecord, InvoiceRecord, Plan, Store, SubscriptionRecord, User


_PAYMENT_STATUS = {"pending", "paid", "failed"}
_ENTITLEMENT_BY_SUBSCRIPTION_STATUS = {
    "pending_payment": "pending_activation",
    "active": "active",
    "past_due": "blocked",
    "canceled": "inactive",
    "manual_review": "manual_review",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _idempotency(namespace: str, company_id: int, key: str) -> str:
    return sha256(f"{namespace}\x1f{company_id}\x1f{key}".encode("utf-8")).hexdigest()


def _scope(db: Session, principal: dict) -> tuple[User, Store, int]:
    user_id = principal.get("user_id")
    store_id = principal.get("store_id")
    user = db.get(User, user_id)
    store = db.get(Store, store_id)
    if user is None or store is None or user.store_id != store.id or store.company_id is None:
        raise HTTPException(status_code=403, detail="Tenant scope denied")
    return user, store, store.company_id


def _plan(db: Session, *, plan_name: str, channel: str) -> Plan:
    plan = db.execute(
        select(Plan).where(Plan.name == plan_name, Plan.channel == channel).order_by(Plan.id.asc())
    ).scalars().first()
    if plan is None:
        raise HTTPException(status_code=422, detail="Plan is unavailable for this channel")
    if not isinstance(plan.monthly_price, int) or isinstance(plan.monthly_price, bool) or plan.monthly_price < 0:
        raise HTTPException(status_code=409, detail="Plan amount is invalid")
    return plan


def _audit(db: Session, *, user_id: int, store_id: int, action: str, resource_type: str, resource_id: int, values: dict) -> None:
    """Audit control state only; caller must not pass PII or raw payment data."""
    db.add(
        AuditLog(
            user_id=user_id,
            store_id=store_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            new_value=values,
        )
    )


async def create_intent(
    db: Session,
    *,
    principal: dict,
    plan_name: str,
    channel: str,
    idempotency_key: str,
    subscription_provider: ISubscriptionProvider,
    payment_provider: Optional[IPaymentProvider] = None,
) -> SubscriptionRecord:
    """Create a payment-gated subscription.  No payment adapter means not initiated."""
    user, store, company_id = _scope(db, principal)
    plan = _plan(db, plan_name=plan_name, channel=channel)
    key = _idempotency("subscription_intent", company_id, idempotency_key)
    existing = db.execute(
        select(SubscriptionRecord).where(
            SubscriptionRecord.company_id == company_id,
            SubscriptionRecord.idempotency_key == key,
        )
    ).scalars().first()
    if existing is not None:
        return existing

    now = _utcnow()
    decision = subscription_provider.start(
        SubscriptionIntent(
            company_id=company_id,
            store_id=store.id,
            user_id=user.id,
            plan_id=plan.id,
            channel=channel,
            idempotency_key=key,
        ),
        now=now,
    )
    status = decision.status if decision.status == "pending_payment" else "manual_review"
    subscription = SubscriptionRecord(
        company_id=company_id,
        store_id=store.id,
        user_id=user.id,
        plan_id=plan.id,
        channel=channel,
        status=status,
        entitlement_status=_ENTITLEMENT_BY_SUBSCRIPTION_STATUS[status],
        idempotency_key=key,
    )
    db.add(subscription)
    db.flush()
    billing = BillingRecord(
        user_id=user.id,
        store_id=store.id,
        amount=plan.monthly_price,
        currency=plan.currency,
        status="pending",
        payment_method="delegated" if payment_provider else "not_initiated",
        description="orderai_subscription_intent",
    )
    db.add(billing)
    db.flush()

    payment_status = "not_initiated"
    payment_reason_code = None
    if payment_provider is not None:
        try:
            payment = await payment_provider.create_payment(
                PaymentRequest(
                    tenant_id=store.id,
                    order_id=billing.id,
                    amount=plan.monthly_price,
                    currency=plan.currency,
                    description="orderai_subscription",
                )
            )
            payment_status = payment.status if payment.status in _PAYMENT_STATUS else "manual_review"
            if payment_status == "manual_review":
                payment_reason_code = "UNKNOWN_PAYMENT_STATUS"
            subscription.payment_reference = payment.reference
            billing.status = payment_status if payment_status != "manual_review" else "manual_review"
            if payment_status == "paid":
                status = subscription_provider.transition(current_status=subscription.status, action="payment_confirmed", now=now).status
                subscription.status = status if status == "active" else "manual_review"
                if subscription.status == "active":
                    period_days = get_settings().subscription_period_days
                    if not isinstance(period_days, int) or isinstance(period_days, bool) or period_days <= 0:
                        subscription.status = "manual_review"
                    else:
                        subscription.current_period_end = now + timedelta(days=period_days)
            elif payment_status == "manual_review":
                subscription.status = "manual_review"
        except TimeoutError:
            payment_status = "manual_review"
            billing.status = "manual_review"
            subscription.status = "manual_review"
            payment_reason_code = "PAYMENT_PROVIDER_TIMEOUT"
        except Exception:
            payment_status = "manual_review"
            billing.status = "manual_review"
            subscription.status = "manual_review"
            payment_reason_code = "PAYMENT_PROVIDER_ERROR"

    subscription.entitlement_status = _ENTITLEMENT_BY_SUBSCRIPTION_STATUS.get(subscription.status, "manual_review")
    _audit(
        db,
        user_id=user.id,
        store_id=store.id,
        action="subscription.intent.created",
        resource_type="subscription",
        resource_id=subscription.id,
        values={
            "status": subscription.status,
            "channel": channel,
            "payment_status": payment_status,
            **({"reason_code": payment_reason_code} if payment_reason_code else {}),
        },
    )
    db.commit()
    db.refresh(subscription)
    return subscription


def apply_action(
    db: Session,
    *,
    principal: dict,
    action: str,
    idempotency_key: str,
    subscription_provider: ISubscriptionProvider,
    target_plan_name: str | None = None,
) -> SubscriptionRecord:
    """Applies customer-permitted actions; unknown or out-of-state action stays manual_review."""
    user, store, company_id = _scope(db, principal)
    subscription = db.execute(
        select(SubscriptionRecord)
        .where(
            SubscriptionRecord.company_id == company_id,
            SubscriptionRecord.store_id == store.id,
            SubscriptionRecord.user_id == user.id,
        )
        .order_by(SubscriptionRecord.id.desc())
    ).scalars().first()
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    action_key = _idempotency(f"subscription_action:{subscription.id}:{action}", company_id, idempotency_key)
    previous = db.execute(
        select(AuditLog).where(
            AuditLog.store_id == store.id,
            AuditLog.action == "subscription.action.applied",
            AuditLog.new_value["idempotency_key"].astext == action_key,
        )
    ).scalars().first()
    if previous is not None:
        return subscription

    if action == "change_plan":
        if not target_plan_name:
            raise HTTPException(status_code=422, detail="Target plan is required")
        target = _plan(db, plan_name=target_plan_name, channel=subscription.channel)
        subscription.plan_id = target.id
    decision = subscription_provider.transition(current_status=subscription.status, action=action, now=_utcnow())
    subscription.status = decision.status
    subscription.entitlement_status = _ENTITLEMENT_BY_SUBSCRIPTION_STATUS.get(subscription.status, "manual_review")
    if decision.status == "canceled":
        subscription.canceled_at = decision.effective_at
    _audit(
        db,
        user_id=user.id,
        store_id=store.id,
        action="subscription.action.applied",
        resource_type="subscription",
        resource_id=subscription.id,
        values={"action": action, "status": subscription.status, "reason_code": decision.reason_code, "idempotency_key": action_key},
    )
    db.commit()
    db.refresh(subscription)
    return subscription


def reconcile_payment_status(
    db: Session,
    *,
    subscription: SubscriptionRecord,
    payment_status: str,
    subscription_provider: ISubscriptionProvider,
) -> SubscriptionRecord:
    """Trusted adapter/scheduler-only payment reconciliation; never expose as a public client action."""
    action_by_status = {"paid": "payment_confirmed", "failed": "mark_past_due"}
    action = action_by_status.get(payment_status)
    if action is None:
        decision_status = "manual_review"
        reason_code = "UNKNOWN_PAYMENT_STATUS"
    else:
        decision = subscription_provider.transition(
            current_status=subscription.status,
            action=action,
            now=_utcnow(),
        )
        decision_status = decision.status
        reason_code = decision.reason_code
    subscription.status = decision_status
    if decision_status == "active":
        period_days = get_settings().subscription_period_days
        if isinstance(period_days, int) and not isinstance(period_days, bool) and period_days > 0:
            subscription.current_period_end = _utcnow() + timedelta(days=period_days)
        else:
            subscription.status = "manual_review"
    subscription.entitlement_status = _ENTITLEMENT_BY_SUBSCRIPTION_STATUS.get(subscription.status, "manual_review")
    _audit(
        db,
        user_id=subscription.user_id,
        store_id=subscription.store_id,
        action="subscription.payment.reconciled",
        resource_type="subscription",
        resource_id=subscription.id,
        values={"status": subscription.status, "payment_status": payment_status if payment_status in _PAYMENT_STATUS else "unknown", "reason_code": reason_code},
    )
    db.commit()
    db.refresh(subscription)
    return subscription


def request_invoice(
    db: Session,
    *,
    principal: dict,
    subscription: SubscriptionRecord,
    invoice_provider: IInvoiceProvider,
    idempotency_key: str,
) -> InvoiceRecord:
    """Requests invoice through provider; local unconfigured provider returns manual_review."""
    user, store, company_id = _scope(db, principal)
    if subscription.company_id != company_id or subscription.store_id != store.id or subscription.user_id != user.id:
        raise HTTPException(status_code=403, detail="Tenant scope denied")
    if subscription.status != "active":
        raise HTTPException(status_code=409, detail="Entitlement is not active")
    plan = db.get(Plan, subscription.plan_id)
    if plan is None or not isinstance(plan.monthly_price, int) or isinstance(plan.monthly_price, bool):
        raise HTTPException(status_code=409, detail="Plan amount is invalid")
    key = _idempotency(f"invoice:{subscription.id}", company_id, idempotency_key)
    existing = db.execute(
        select(InvoiceRecord).where(InvoiceRecord.company_id == company_id, InvoiceRecord.idempotency_key == key)
    ).scalars().first()
    if existing is not None:
        return existing
    result = invoice_provider.issue(
        InvoiceRequest(
            company_id=company_id,
            store_id=store.id,
            user_id=user.id,
            subscription_id=subscription.id,
            amount_minor=plan.monthly_price,
            currency=plan.currency,
            idempotency_key=key,
        )
    )
    status = result.status if result.status in {"pending", "issued", "manual_review", "void"} else "manual_review"
    invoice = InvoiceRecord(
        company_id=company_id,
        store_id=store.id,
        user_id=user.id,
        subscription_id=subscription.id,
        amount_minor=plan.monthly_price,
        currency=plan.currency,
        status=status,
        provider_reference=result.reference,
        idempotency_key=key,
        issued_at=_utcnow() if status == "issued" else None,
    )
    db.add(invoice)
    db.flush()
    _audit(
        db,
        user_id=user.id,
        store_id=store.id,
        action="invoice.requested",
        resource_type="invoice",
        resource_id=invoice.id,
        values={"status": status, "reason_code": result.reason_code},
    )
    db.commit()
    db.refresh(invoice)
    return invoice


def status_for_principal(db: Session, *, principal: dict) -> tuple[SubscriptionRecord, Plan, User, str, str]:
    """Returns only data required for public status serialization; scope comes from principal."""
    user, store, company_id = _scope(db, principal)
    subscription = db.execute(
        select(SubscriptionRecord)
        .where(
            SubscriptionRecord.company_id == company_id,
            SubscriptionRecord.store_id == store.id,
            SubscriptionRecord.user_id == user.id,
        )
        .order_by(SubscriptionRecord.id.desc())
    ).scalars().first()
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    plan = db.get(Plan, subscription.plan_id)
    if plan is None:
        raise HTTPException(status_code=409, detail="Subscription plan not found")
    billing = db.execute(
        select(BillingRecord)
        .where(BillingRecord.user_id == user.id, BillingRecord.store_id == store.id)
        .order_by(BillingRecord.id.desc())
    ).scalars().first()
    invoice = db.execute(
        select(InvoiceRecord)
        .where(InvoiceRecord.company_id == company_id, InvoiceRecord.subscription_id == subscription.id)
        .order_by(InvoiceRecord.id.desc())
    ).scalars().first()
    payment_status = billing.status if billing and billing.status in {"pending", "paid", "failed", "manual_review"} else "manual_review"
    return subscription, plan, user, payment_status, invoice.status if invoice else "not_requested"


def latest_invoice_for_principal(db: Session, *, principal: dict) -> InvoiceRecord:
    """Returns only the principal's latest invoice-status record, never cross-company data."""
    user, store, company_id = _scope(db, principal)
    invoice = db.execute(
        select(InvoiceRecord)
        .where(
            InvoiceRecord.company_id == company_id,
            InvoiceRecord.store_id == store.id,
            InvoiceRecord.user_id == user.id,
        )
        .order_by(InvoiceRecord.id.desc())
    ).scalars().first()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice
