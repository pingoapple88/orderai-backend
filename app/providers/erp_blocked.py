"""BlockedErpIngestProvider — ENG-03 未就緒前的 fail-closed 佔位實作。

WO-04 §4 強制停止：未取得雲鼎 owner / sandbox / 書面待確認訂單契約前，
不連線、不硬編 endpoint、不送任何資料。本實作對任何呼叫一律 raise
ErpIngestBlockedError，且不做任何網路動作。
"""
from app.core.interfaces.erp_ingest import (
    ErpIngestBlockedError,
    ErpIngestRequest,
    ErpIngestResult,
    IErpIngestProvider,
    PendingConfirmationOrderRequest,
    PendingCustomerRequest,
)


class BlockedErpIngestProvider(IErpIngestProvider):
    name = "blocked"

    async def submit_pending_order(self, request: ErpIngestRequest) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONNECTION_BLOCKED",
            "雲鼎 ERP owner/sandbox/書面契約未就緒；依 WO-04 §4 不送資料。",
        )

    async def create_pending_customer(self, request: PendingCustomerRequest) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONNECTION_BLOCKED",
            "雲鼎 ERP owner/sandbox/書面契約未就緒；依 P1 規則不送待確認客戶資料。",
        )

    async def submit_pending_confirmation_order(
        self, request: PendingConfirmationOrderRequest
    ) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONNECTION_BLOCKED",
            "雲鼎 ERP owner/sandbox/書面契約未就緒；依 P1 規則不送待確認訂單資料。",
        )
