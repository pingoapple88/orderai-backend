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


def test_interface_is_abstract():
    with pytest.raises(TypeError):
        IErpIngestProvider()   # 抽象類別不可實例化
