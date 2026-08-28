"""Day 31–60 read models remain company/store principal-scoped and fail closed."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import AIUsageLog, BillingRecord
from app.providers.local_subscription import LocalSubscriptionProvider
from app.services import subscription_service
from tests.test_subscription_service import _principal_with_plan


@pytest.mark.asyncio
async def test_usage_history_and_billing_history_are_scoped_and_utc(db_session):
    principal, plan = _principal_with_plan(db_session)
    subscription = await subscription_service.create_intent(
        db_session,
        principal=principal,
        plan_name=plan.name,
        channel="direct",
        idempotency_key="query-subscription-001",
        subscription_provider=LocalSubscriptionProvider(),
    )
    subscription.status = "active"
    subscription.entitlement_status = "active"
    db_session.add(
        AIUsageLog(
            user_id=principal["user_id"],
            store_id=principal["store_id"],
            usage_date=date.today(),
            usage_count=4,
        )
    )
    db_session.add(
        AIUsageLog(
            user_id=principal["user_id"],
            store_id=principal["store_id"],
            usage_date=date.today() - timedelta(days=40),
            usage_count=99,
        )
    )
    db_session.commit()

    usage = subscription_service.usage_status_for_principal(db_session, principal=principal)
    assert usage["used"] == 4
    assert usage["limit"] == 100
    assert usage["remaining"] == 96
    assert usage["status"] == "available"
    assert usage["cycle_started_at"].tzinfo == timezone.utc

    history = subscription_service.billing_history_for_principal(db_session, principal=principal)
    assert len(history) == 1
    assert history[0]["amount_minor"] == 12345
    assert history[0]["status"] == "pending"
    assert history[0]["created_at"].tzinfo == timezone.utc
    assert "description" not in history[0]


@pytest.mark.asyncio
async def test_usage_fails_closed_when_entitlement_is_not_active(db_session):
    principal, plan = _principal_with_plan(db_session)
    await subscription_service.create_intent(
        db_session,
        principal=principal,
        plan_name=plan.name,
        channel="direct",
        idempotency_key="query-pending-001",
        subscription_provider=LocalSubscriptionProvider(),
    )
    status = subscription_service.usage_status_for_principal(db_session, principal=principal)
    assert status["status"] == "manual_review"
    assert status["remaining"] is None
