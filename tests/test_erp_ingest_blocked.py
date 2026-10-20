"""WO-04 ENG-03：ERP 入站 Adapter 一律 fail-closed（ERP_CONNECTION_BLOCKED）。

證明：未取得雲鼎 owner/sandbox/書面契約前，工廠回傳的 provider 對任何呼叫
一律 raise ErpIngestBlockedError，且不做網路動作、不回假成功（§4）。
"""
import asyncio

import pytest

from app.core.interfaces.erp_ingest import (
    ErpIngestBlockedError,
    ErpIngestItem,
    ErpIngestRequest,
    IErpIngestProvider,
    PendingConfirmationOrderItem,
    PendingConfirmationOrderRequest,
    PendingCustomerRequest,
)
from app.providers import get_erp_ingest_provider


def _req():
    return ErpIngestRequest(
        company_id=1, order_id=1, idempotency_key="idem-1",
        currency="TWD", currency_exponent=0,
        items=[ErpIngestItem(resolved_sku="EGG-30", quantity=2,
                             unit_price_minor=12000, price_source="CATALOG")],
    )


def test_factory_returns_blocked_provider():
    p = get_erp_ingest_provider()
    assert isinstance(p, IErpIngestProvider)


def test_submit_raises_blocked_with_reason_code():
    p = get_erp_ingest_provider()
    with pytest.raises(ErpIngestBlockedError) as ei:
        asyncio.run(p.submit_pending_order(_req()))
    assert ei.value.reason_code == "ERP_CONNECTION_BLOCKED"


def test_pending_customer_and_order_also_raise_blocked():
    p = get_erp_ingest_provider()
    customer = PendingCustomerRequest(
        company_id=1, store_id=1, idempotency_key="pc-1", line_user_id="Utest",
        display_name="測試客戶", phone=None, contact_authorized=True, source_channel="line",
    )
    order = PendingConfirmationOrderRequest(
        company_id=1, store_id=1, sales_location_id=1, idempotency_key="po-1",
        source_event_id="evt-1", buyer_line_user_id="Utest", buyer_name="測試客戶",
        requested_for="2026-09-20", special_request=None,
        items=[PendingConfirmationOrderItem(product_name="測試品項", quantity=1, unit="個", product_id=None)],
    )
    with pytest.raises(ErpIngestBlockedError) as customer_error:
        asyncio.run(p.create_pending_customer(customer))
    with pytest.raises(ErpIngestBlockedError) as order_error:
        asyncio.run(p.submit_pending_confirmation_order(order))
    assert customer_error.value.reason_code == order_error.value.reason_code == "ERP_CONNECTION_BLOCKED"


def test_interface_is_abstract():
    with pytest.raises(TypeError):
        IErpIngestProvider()   # 抽象類別不可實例化
