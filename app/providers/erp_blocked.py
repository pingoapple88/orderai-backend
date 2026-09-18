"""BlockedErpIngestProvider — 未就緒 ERP 的 fail-closed 佔位實作。

未取得對應 ERP owner、sandbox 與書面待確認訂單契約前，不連線、不硬編 endpoint、
不送任何資料。本實作對任何呼叫一律 raise ErpIngestBlockedError。
"""
from app.core.interfaces.erp_ingest import (
    ErpIngestBlockedError,
    ErpIngestRequest,
    ErpIngestResult,
    IErpIngestProvider,
    PendingConfirmationOrderRequest,
    PendingCustomerRequest,
    PendingOrderIntent,
)


class BlockedErpIngestProvider(IErpIngestProvider):
    name = "blocked"

    async def submit_pending_order(self, request: ErpIngestRequest) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONNECTION_BLOCKED",
            "ERP owner/sandbox/書面契約未就緒；不送資料。",
        )

    async def create_pending_customer(self, request: PendingCustomerRequest) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONNECTION_BLOCKED",
            "ERP owner/sandbox/書面契約未就緒；不送待確認客戶資料。",
        )

    async def submit_pending_confirmation_order(
        self, request: PendingConfirmationOrderRequest
    ) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONNECTION_BLOCKED",
            "ERP owner/sandbox/書面契約未就緒；不送待確認訂單資料。",
        )

    async def submit_pending_confirmation_intent(
        self, request: PendingOrderIntent
    ) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONNECTION_BLOCKED",
            "ERP owner/sandbox/書面契約未就緒；不送 provider-neutral 待確認意圖。",
        )
