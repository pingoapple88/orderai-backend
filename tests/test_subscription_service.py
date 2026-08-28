"""Synthetic tests for the T5 self-service subscription lifecycle."""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.interfaces.payment_provider import IPaymentProvider, PaymentRequest, PaymentResult
from app.models import AuditLog, BillingRecord, Company, InvoiceRecord, Plan, Store, SubscriptionRecord, User
from app.providers.local_subscription import LocalManualReviewInvoiceProvider, LocalSubscriptionProvider
from app.services import subscription_service


class StubPaymentProvider(IPaymentProvider):
    def __init__(self, status: str = "pending", raises: bool = False, timeout: bool = False) -> None:
        self.status = status
        self.raises = raises
        self.timeout = timeout
        self.requests: list[PaymentRequest] = []

    async def create_payment(self, request: PaymentRequest) -> PaymentResult:
        self.requests.append(request)
        if self.timeout:
            raise TimeoutError("synthetic provider timeout")
        if self.raises:
            raise RuntimeError("synthetic provider failure")
        return PaymentResult(provider="mock", reference="synthetic-payment-reference", status=self.status)

    async def get_status(self, reference: str) -> PaymentResult:
        return PaymentResult(provider="mock", reference=reference, status=self.status)


def _principal_with_plan(db_session, *, channel: str = "direct", name: str = "synthetic-plan") -> tuple[dict, Plan]:
    company = Company(name="Synthetic Company")
    db_session.add(company)
    db_session.flush()
    store = Store(name="Synthetic Store", company_id=company.id, plan=name)
    plan = Plan(name=name, channel=channel, monthly_price=12345, currency="TWD", ai_extraction_limit=100)
    db_session.add_all([store, plan])
    db_session.flush()
    user = User(line_id=f"U_subscription_test_{name}", plan_id=plan.id, store_id=store.id, ai_usage_count=3)
    db_session.add(user)
    db_session.commit()
    return {"user_id": user.id, "store_id": store.id, "role": "owner"}, plan


@pytest.mark.asyncio
async def test_intent_is_company_scoped_idempotent_and_pending_without_payment(db_session):
    principal, plan = _principal_with_plan(db_session)

    first = await subscription_service.create_intent(
        db_session,
        principal=principal,
        plan_name=plan.name,
        channel="direct",
        idempotency_key="subscription-intent-001",
        subscription_provider=LocalSubscriptionProvider(),
    )
    second = await subscription_service.create_intent(
        db_session,
        principal=principal,
        plan_name=plan.name,
        channel="direct",
        idempotency_key="subscription-intent-001",
        subscription_provider=LocalSubscriptionProvider(),
    )

    assert first.id == second.id
    assert first.status == "pending_payment"
    assert first.entitlement_status == "pending_activation"
    assert len(db_session.execute(select(SubscriptionRecord)).scalars().all()) == 1
    billing = db_session.execute(select(BillingRecord)).scalar_one()
    assert billing.status == "pending" and billing.payment_method == "not_initiated"
    assert billing.amount == 12345 and isinstance(billing.amount, int)
    audit = db_session.execute(select(AuditLog)).scalar_one()
    assert audit.new_value == {"status": "pending_payment", "channel": "direct", "payment_status": "not_initiated"}


@pytest.mark.asyncio
async def test_paid_adapter_can_activate_entitlement_but_unknown_or_failure_is_manual_review(db_session):
    principal, plan = _principal_with_plan(db_session)
    paid = StubPaymentProvider(status="paid")
    active = await subscription_service.create_intent(
        db_session,
        principal=principal,
        plan_name=plan.name,
        channel="direct",
        idempotency_key="subscription-paid-001",
        subscription_provider=LocalSubscriptionProvider(),
        payment_provider=paid,
    )
    assert active.status == "active"
    assert active.entitlement_status == "active"
    assert paid.requests[0].amount == 12345
    assert active.current_period_end is not None
    assert active.current_period_end.tzinfo == timezone.utc
    assert active.current_period_end > datetime.now(timezone.utc)

    other_principal, other_plan = _principal_with_plan(db_session, name="synthetic-plan-two")
    unknown = await subscription_service.create_intent(
        db_session,
        principal=other_principal,
        plan_name=other_plan.name,
        channel="direct",
        idempotency_key="subscription-unknown-001",
        subscription_provider=LocalSubscriptionProvider(),
        payment_provider=StubPaymentProvider(status="mystery"),
    )
    assert unknown.status == "manual_review"
    assert unknown.entitlement_status == "manual_review"


@pytest.mark.asyncio
async def test_all_channels_require_their_own_existing_plan(db_session):
    principal, direct_plan = _principal_with_plan(db_session)
    dealer_plan = Plan(name="synthetic-dealer-plan", channel="dealer", monthly_price=12345, currency="TWD")
    enterprise_plan = Plan(name="synthetic-enterprise-plan", channel="enterprise", monthly_price=12345, currency="TWD")
    db_session.add_all([dealer_plan, enterprise_plan])
    db_session.commit()
    for index, plan in enumerate((direct_plan, dealer_plan, enterprise_plan)):
        subscription = await subscription_service.create_intent(
            db_session,
            principal=principal,
            plan_name=plan.name,
            channel=plan.channel,
            idempotency_key=f"subscription-channel-{index}-001",
            subscription_provider=LocalSubscriptionProvider(),
        )
        assert subscription.channel == plan.channel
        assert subscription.status == "pending_payment"
        assert subscription.entitlement_status == "pending_activation"


@pytest.mark.asyncio
async def test_provider_failure_never_auto_activates_and_invoice_stays_manual_review(db_session):
    principal, plan = _principal_with_plan(db_session)
    failed = await subscription_service.create_intent(
        db_session,
        principal=principal,
        plan_name=plan.name,
        channel="direct",
        idempotency_key="subscription-provider-error-001",
        subscription_provider=LocalSubscriptionProvider(),
        payment_provider=StubPaymentProvider(raises=True),
    )
    assert failed.status == "manual_review"
    assert failed.entitlement_status == "manual_review"
    with pytest.raises(HTTPException, match="Entitlement is not active"):
        subscription_service.request_invoice(
            db_session,
            principal=principal,
            subscription=failed,
            invoice_provider=LocalManualReviewInvoiceProvider(),
            idempotency_key="invoice-denied-001",
        )

    active = await subscription_service.create_intent(
        db_session,
        principal=principal,
        plan_name=plan.name,
        channel="direct",
        idempotency_key="subscription-invoice-active-001",
        subscription_provider=LocalSubscriptionProvider(),
        payment_provider=StubPaymentProvider(status="paid"),
    )
    invoice = subscription_service.request_invoice(
        db_session,
        principal=principal,
        subscription=active,
        invoice_provider=LocalManualReviewInvoiceProvider(),
        idempotency_key="invoice-active-001",
    )
    assert invoice.status == "manual_review"
    assert invoice.amount_minor == plan.monthly_price and isinstance(invoice.amount_minor, int)
    assert len(db_session.execute(select(InvoiceRecord)).scalars().all()) == 1
    duplicate = subscription_service.request_invoice(
        db_session,
        principal=principal,
        subscription=active,
        invoice_provider=LocalManualReviewInvoiceProvider(),
        idempotency_key="invoice-active-001",
    )
    assert duplicate.id == invoice.id
    audit_values = db_session.execute(
        select(AuditLog).where(AuditLog.action == "subscription.intent.created").order_by(AuditLog.id.asc())
    ).scalars().first().new_value
    assert "payment_reference" not in audit_values and "provider_reference" not in audit_values

    timeout = await subscription_service.create_intent(
        db_session,
        principal=principal,
        plan_name=plan.name,
        channel="direct",
        idempotency_key="subscription-provider-timeout-001",
        subscription_provider=LocalSubscriptionProvider(),
        payment_provider=StubPaymentProvider(timeout=True),
    )
    assert timeout.status == "manual_review"
    assert timeout.entitlement_status == "manual_review"
    timeout_audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "subscription.intent.created").order_by(AuditLog.id.desc())
    ).scalars().first()
    assert timeout_audit.new_value["reason_code"] == "PAYMENT_PROVIDER_TIMEOUT"


@pytest.mark.asyncio
async def test_renew_change_cancel_and_cross_company_access_follow_fail_closed_rules(db_session):
    principal, plan = _principal_with_plan(db_session)
    second_plan = Plan(name="synthetic-plan-next", channel="direct", monthly_price=23456, currency="TWD")
    db_session.add(second_plan)
    db_session.commit()
    active = await subscription_service.create_intent(
        db_session,
        principal=principal,
        plan_name=plan.name,
        channel="direct",
        idempotency_key="subscription-actions-001",
        subscription_provider=LocalSubscriptionProvider(),
        payment_provider=StubPaymentProvider(status="paid"),
    )
    renewed = subscription_service.apply_action(
        db_session,
        principal=principal,
        action="renew",
        idempotency_key="subscription-renew-001",
        subscription_provider=LocalSubscriptionProvider(),
    )
    assert renewed.status == "pending_payment"
    assert renewed.entitlement_status == "pending_activation"
    renewed.status = "active"
    db_session.commit()
    changed = subscription_service.apply_action(
        db_session,
        principal=principal,
        action="change_plan",
        target_plan_name=second_plan.name,
        idempotency_key="subscription-change-001",
        subscription_provider=LocalSubscriptionProvider(),
    )
    assert changed.plan_id == second_plan.id and changed.status == "pending_payment"
    assert changed.entitlement_status == "pending_activation"
    changed.status = "active"
    db_session.commit()
    cancelled = subscription_service.apply_action(
        db_session,
        principal=principal,
        action="cancel",
        idempotency_key="subscription-cancel-001",
        subscription_provider=LocalSubscriptionProvider(),
    )
    assert cancelled.status == "canceled"
    assert cancelled.entitlement_status == "inactive"
    assert cancelled.canceled_at is not None and cancelled.canceled_at.tzinfo == timezone.utc

    with pytest.raises(HTTPException, match="Tenant scope denied"):
        subscription_service.status_for_principal(db_session, principal={"user_id": principal["user_id"], "store_id": 999999})

    decision = LocalSubscriptionProvider().transition(current_status="unknown", action="cancel", now=datetime.now(timezone.utc))
    assert decision.status == "manual_review" and decision.reason_code == "UNKNOWN_TRANSITION"


@pytest.mark.asyncio
async def test_trusted_payment_reconciliation_supports_overdue_but_unknown_is_manual_review(db_session):
    principal, plan = _principal_with_plan(db_session)
    subscription = await subscription_service.create_intent(
        db_session,
        principal=principal,
        plan_name=plan.name,
        channel="direct",
        idempotency_key="subscription-reconcile-001",
        subscription_provider=LocalSubscriptionProvider(),
    )
    overdue = subscription_service.reconcile_payment_status(
        db_session,
        subscription=subscription,
        payment_status="failed",
        subscription_provider=LocalSubscriptionProvider(),
    )
    assert overdue.status == "past_due"
    assert overdue.entitlement_status == "blocked"
    unknown = subscription_service.reconcile_payment_status(
        db_session,
        subscription=overdue,
        payment_status="unexpected",
        subscription_provider=LocalSubscriptionProvider(),
    )
    assert unknown.status == "manual_review"
    assert unknown.entitlement_status == "manual_review"
    audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "subscription.payment.reconciled").order_by(AuditLog.id.desc())
    ).scalars().first()
    assert audit.new_value == {"status": "manual_review", "payment_status": "unknown", "reason_code": "UNKNOWN_PAYMENT_STATUS"}
