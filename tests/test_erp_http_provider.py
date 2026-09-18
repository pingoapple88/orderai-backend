import asyncio
import hashlib
import hmac
import json

import httpx

from app.core.interfaces.erp_ingest import (
    ErpIngestBlockedError,
    PendingConfirmationOrderItem,
    PendingConfirmationOrderRequest,
    PendingCustomerRequest,
)
from app.providers import get_erp_ingest_provider, settings
from app.providers.erp_blocked import BlockedErpIngestProvider
from app.providers.erp_http import CloudDingErpIngestProvider


def _provider(handler):
    return CloudDingErpIngestProvider(
        base_url="https://erp.test.invalid",
        service_id="orderai_p1",
        ingress_hmac_secret="synthetic-test-secret",
        transport=httpx.MockTransport(handler),
    )


def test_erp_factory_defaults_to_blocked_and_requires_complete_http_settings(monkeypatch):
    monkeypatch.setattr(settings, "p1_erp_ingest_provider", "blocked")
    assert isinstance(get_erp_ingest_provider(), BlockedErpIngestProvider)

    monkeypatch.setattr(settings, "p1_erp_ingest_provider", "http")
    monkeypatch.setattr(settings, "p1_erp_base_url", "https://erp.test.invalid")
    monkeypatch.setattr(settings, "p1_erp_service_id", "orderai_p1")
    monkeypatch.setattr(settings, "p1_erp_ingress_hmac_secret", "")
    assert isinstance(get_erp_ingest_provider(), BlockedErpIngestProvider)

    monkeypatch.setattr(settings, "p1_erp_ingress_hmac_secret", "synthetic-test-secret")
    monkeypatch.setattr(settings, "p1_erp_timeout_seconds", 10)
    provider = get_erp_ingest_provider()
    assert isinstance(provider, CloudDingErpIngestProvider)
    assert provider.base_url == "https://erp.test.invalid"


def test_http_provider_signs_and_normalizes_pending_customer_and_order_requests():
    requests = []

    def handler(request):
        body = request.content
        canonical = b"\n".join([
            request.headers["X-P1-Service-Id"].encode(),
            request.headers["X-P1-Timestamp"].encode(),
            request.headers["X-P1-Nonce"].encode(),
            body,
        ])
        expected = hmac.new(b"synthetic-test-secret", canonical, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(expected, request.headers["X-P1-Signature"])
        requests.append((request.url.path, json.loads(body)))
        if request.url.path.endswith("pending-customers/service/ingest"):
            return httpx.Response(201, json={"id": 41})
        return httpx.Response(201, json={"id": 42, "reference_no": "PCO-TEST-42"})

    provider = _provider(handler)
    customer = PendingCustomerRequest(
        company_id=7, store_id=3, sales_location_id=9, idempotency_key="customer-0001", line_user_id="U-synthetic",
        display_name="合成客戶", phone="0900000000", contact_authorized=True, source_channel="line",
    )
    order = PendingConfirmationOrderRequest(
        company_id=7, store_id=3, sales_location_id=9, idempotency_key="order-0001",
        source_event_id="evt-synthetic", pending_customer_id=41, buyer_line_user_id="U-synthetic",
        buyer_name="合成客戶", requested_for="2026-09-20T02:00:00+00:00", special_request="送達前電話確認",
        items=[PendingConfirmationOrderItem(product_name="合成品項", quantity=2, unit="盒", product_id=81)],
    )

    customer_result = asyncio.run(provider.create_pending_customer(customer))
    order_result = asyncio.run(provider.submit_pending_confirmation_order(order))

    assert customer_result.reference == "41"
    assert order_result.reference == "PCO-TEST-42"
    assert requests[0][0] == "/api/pending-customers/service/ingest"
    assert requests[0][1]["sales_location_id"] == 9
    assert requests[0][1]["source_material_hash"] == hashlib.sha256(b"customer-0001").hexdigest()
    assert requests[1][0] == "/api/pending-confirmation-orders/service/ingest"
    assert requests[1][1]["pending_customer_id"] == 41
    assert requests[1][1]["items"] == [{"product_id": 81, "quantity": 2}]
    assert "payment_method" not in requests[1][1]
    assert "warehouse_id" not in requests[1][1]


def test_http_provider_rejects_error_response_without_exposing_payload():
    provider = _provider(lambda request: httpx.Response(503, json={"detail": "unavailable"}))
    request = PendingCustomerRequest(
        company_id=7, store_id=3, sales_location_id=9, idempotency_key="customer-0002", line_user_id=None,
        display_name="合成客戶", phone=None, contact_authorized=False, source_channel="line",
    )
    try:
        asyncio.run(provider.create_pending_customer(request))
    except ErpIngestBlockedError as exc:
        assert exc.reason_code == "ERP_INGEST_REJECTED"
        assert "合成客戶" not in str(exc)
    else:
        raise AssertionError("ERP error response must fail closed")
