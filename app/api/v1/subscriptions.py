"""OrderAI independent subscription endpoints; all customer scope comes from JWT principal."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_principal
from app.core.response import success_response
from app.providers import get_invoice_provider, get_payment_provider, get_subscription_provider
from app.schemas import InvoiceRequestCreate, InvoiceStatusOut, SubscriptionActionCreate, SubscriptionIntentCreate, SubscriptionOut
from app.services import subscription_service


router = APIRouter()


def _serialize(subscription, plan, user, payment_status: str, invoice_status: str) -> dict:
    return SubscriptionOut(
        status=subscription.status,
        entitlement_status=subscription.entitlement_status,
        channel=subscription.channel,
        plan_name=plan.name,
        ai_usage_count=user.ai_usage_count,
        ai_extraction_limit=plan.ai_extraction_limit,
        current_period_end=subscription.current_period_end,
        payment_status=payment_status,
        invoice_status=invoice_status,
    ).model_dump(by_alias=True)


@router.post("/intents", status_code=201)
async def create_intent(
    payload: SubscriptionIntentCreate,
    principal: dict = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    subscription = await subscription_service.create_intent(
        db,
        principal=principal,
        plan_name=payload.plan_name,
        channel=payload.channel,
        idempotency_key=payload.idempotency_key,
        subscription_provider=get_subscription_provider(),
        payment_provider=get_payment_provider(),
    )
    current, plan, user, payment_status, invoice_status = subscription_service.status_for_principal(db, principal=principal)
    return success_response(_serialize(current, plan, user, payment_status, invoice_status))


@router.get("/status")
def subscription_status(
    principal: dict = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    subscription, plan, user, payment_status, invoice_status = subscription_service.status_for_principal(db, principal=principal)
    return success_response(_serialize(subscription, plan, user, payment_status, invoice_status))


@router.post("/actions")
def subscription_action(
    payload: SubscriptionActionCreate,
    principal: dict = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    subscription_service.apply_action(
        db,
        principal=principal,
        action=payload.action,
        idempotency_key=payload.idempotency_key,
        target_plan_name=payload.target_plan_name,
        subscription_provider=get_subscription_provider(),
    )
    subscription, plan, user, payment_status, invoice_status = subscription_service.status_for_principal(db, principal=principal)
    return success_response(_serialize(subscription, plan, user, payment_status, invoice_status))


@router.post("/invoices", status_code=201)
def request_invoice(
    payload: InvoiceRequestCreate,
    principal: dict = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    subscription, _, _, _, _ = subscription_service.status_for_principal(db, principal=principal)
    invoice = subscription_service.request_invoice(
        db,
        principal=principal,
        subscription=subscription,
        invoice_provider=get_invoice_provider(),
        idempotency_key=payload.idempotency_key,
    )
    return success_response(InvoiceStatusOut.model_validate(invoice).model_dump(by_alias=True))


@router.get("/invoices/latest")
def latest_invoice(
    principal: dict = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    invoice = subscription_service.latest_invoice_for_principal(db, principal=principal)
    return success_response(InvoiceStatusOut.model_validate(invoice).model_dump(by_alias=True))
