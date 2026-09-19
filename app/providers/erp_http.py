"""Existing CloudDing ERP HTTP Adapter.

This class remains unrelated to Jiezhou.  Its configured transport is unchanged;
Jiezhou has no HTTP implementation in this branch because its contract is unknown.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.interfaces.erp_ingest import (
    ErpIngestBlockedError,
    ErpIngestRequest,
    ErpIngestResult,
    IErpIngestProvider,
    PendingConfirmationOrderRequest,
    PendingCustomerRequest,
    PendingOrderIntent,
)


@dataclass
class CloudDingErpIngestProvider(IErpIngestProvider):
    """使用 P1 service-to-service HMAC 的既有雲鼎待確認資料 Adapter。"""

    base_url: str
    service_id: str
    ingress_hmac_secret: str
    timeout_seconds: int = 10
    transport: Optional[httpx.AsyncBaseTransport] = None

    _CUSTOMER_PATH = "/api/pending-customers/service/ingest"
    _ORDER_PATH = "/api/pending-confirmation-orders/service/ingest"

    def _require_ready(self) -> None:
        if (
            not self.base_url.strip()
            or not self.service_id.strip()
            or not self.ingress_hmac_secret.strip()
            or self.timeout_seconds <= 0
        ):
            raise ErpIngestBlockedError("ERP_CONNECTION_BLOCKED", "ERP HTTP Adapter 安全設定未完成")
        if not self.base_url.startswith(("https://", "http://")):
            raise ErpIngestBlockedError("ERP_CONNECTION_BLOCKED", "ERP HTTP Adapter 端點格式無效")

    def _headers(self, body: bytes) -> dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        canonical = b"\n".join([self.service_id.encode(), timestamp.encode(), nonce.encode(), body])
        signature = hmac.new(self.ingress_hmac_secret.encode(), canonical, hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-P1-Service-Id": self.service_id,
            "X-P1-Timestamp": timestamp,
            "X-P1-Nonce": nonce,
            "X-P1-Signature": signature,
        }

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_ready()
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = await client.post(f"{self.base_url.rstrip('/')}{path}", content=body, headers=self._headers(body))
        if response.status_code not in {200, 201}:
            raise ErpIngestBlockedError("ERP_INGEST_REJECTED", f"ERP 回應狀態：{response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ErpIngestBlockedError("ERP_INGEST_INVALID_RESPONSE", "ERP 回應格式無效") from exc
        if not isinstance(data, dict) or not data.get("id"):
            raise ErpIngestBlockedError("ERP_INGEST_INVALID_RESPONSE", "ERP 回應缺少待確認資料識別碼")
        return data

    async def create_pending_customer(self, request: PendingCustomerRequest) -> ErpIngestResult:
        data = await self._post(
            self._CUSTOMER_PATH,
            {
                "company_id": request.company_id,
                "sales_location_id": request.sales_location_id,
                "source": "orderai_line",
                "idempotency_key": request.idempotency_key,
                "source_material_hash": hashlib.sha256(request.idempotency_key.encode()).hexdigest(),
                "line_user_id": request.line_user_id,
                "display_name": request.display_name,
                "phone": request.phone,
                "contact_authorized": request.contact_authorized,
            },
        )
        return ErpIngestResult(provider="cloud_ding_http", reference=str(data["id"]), status="accepted")

    async def submit_pending_confirmation_order(
        self, request: PendingConfirmationOrderRequest
    ) -> ErpIngestResult:
        data = await self._post(
            self._ORDER_PATH,
            {
                "company_id": request.company_id,
                "sales_location_id": request.sales_location_id,
                "pending_customer_id": request.pending_customer_id,
                "customer_name": request.buyer_name,
                "customer_phone": None,
                "requested_for": request.requested_for,
                "special_request": request.special_request,
                "idempotency_key": request.idempotency_key,
                "source_event_id": request.source_event_id,
                "items": [{"product_id": item.product_id, "quantity": item.quantity} for item in request.items],
            },
        )
        reference = data.get("reference_no") or f"pending_order:{data['id']}"
        return ErpIngestResult(provider="cloud_ding_http", reference=str(reference), status="accepted")

    async def submit_pending_order(self, request: ErpIngestRequest) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONTRACT_MISMATCH",
            "此 Adapter 僅支援既有 P1 待確認客戶與待確認訂單，不能送出一般訂單。",
        )

    async def submit_pending_confirmation_intent(
        self, request: PendingOrderIntent
    ) -> ErpIngestResult:
        raise ErpIngestBlockedError(
            "ERP_CONTRACT_MISMATCH",
            "CloudDing adapter 不可處理捷州 provider-neutral intent；不得轉譯其他 ERP 契約。",
        )
