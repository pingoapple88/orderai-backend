"""API tests: customer scope comes from server principal, never request payload."""
from fastapi.testclient import TestClient

from app.api.v1 import subscriptions
from app.core.database import get_db
from app.core.deps import get_current_principal
from app.core.interfaces.payment_provider import IPaymentProvider, PaymentResult
from app.main import app
from app.models import Company, Plan, Store, User
from app.providers.local_subscription import LocalManualReviewInvoiceProvider, LocalSubscriptionProvider


class PaidProvider(IPaymentProvider):
    async def create_payment(self, request):
        return PaymentResult(provider="mock", reference="synthetic-payment", status="paid")

    async def get_status(self, reference):
        return PaymentResult(provider="mock", reference=reference, status="paid")


def _principal(db_session):
    company = Company(name="T5 Subscription API Company")
    db_session.add(company)
    db_session.flush()
    store = Store(name="T5 Subscription API Store", company_id=company.id, plan="api-plan")
    plan = Plan(name="api-plan", channel="direct", monthly_price=20000, currency="TWD", ai_extraction_limit=50)
    db_session.add_all([store, plan])
    db_session.flush()
    user = User(line_id="U_subscription_api", store_id=store.id, plan_id=plan.id, role="owner", ai_usage_count=2)
    db_session.add(user)
    db_session.commit()
    return {"user_id": user.id, "store_id": store.id, "role": "owner"}


def test_subscription_api_uses_principal_scope_and_returns_minimal_camel_case_data(db_session, monkeypatch):
    principal = _principal(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_principal] = lambda: principal
    monkeypatch.setattr(subscriptions, "get_payment_provider", lambda: PaidProvider())
    monkeypatch.setattr(subscriptions, "get_subscription_provider", lambda: LocalSubscriptionProvider())
    monkeypatch.setattr(subscriptions, "get_invoice_provider", lambda: LocalManualReviewInvoiceProvider())
    client = TestClient(app)
    try:
        invalid_scope = client.post(
            "/api/v1/orderai/subscriptions/intents",
            json={"planName": "api-plan", "channel": "direct", "idempotencyKey": "api-subscription-001", "companyId": 999},
        )
        assert invalid_scope.status_code == 422
        created = client.post(
            "/api/v1/orderai/subscriptions/intents",
            json={"planName": "api-plan", "channel": "direct", "idempotencyKey": "api-subscription-001"},
        )
        assert created.status_code == 201
        data = created.json()["data"]
        assert data["status"] == "active"
        assert data["entitlementStatus"] == "active"
        assert data["paymentStatus"] == "paid"
        assert data["aiExtractionLimit"] == 50
        assert {"companyId", "storeId", "userId", "paymentReference", "providerReference"}.isdisjoint(data)
        invoice = client.post("/api/v1/orderai/subscriptions/invoices", json={"idempotencyKey": "api-invoice-001"})
        assert invoice.status_code == 201
        invoice_data = invoice.json()["data"]
        assert invoice_data["status"] == "manual_review"
        assert invoice_data["amountMinor"] == 20000
        assert "companyId" not in invoice_data and "subscriptionId" not in invoice_data
    finally:
        app.dependency_overrides.clear()
