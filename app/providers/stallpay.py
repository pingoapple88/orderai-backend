"""IPaymentProvider 的 StallPay 實作（情境四：金流橋接 + 被動接收 + 主動輪詢）。

OrderAI 不碰金流：建立付款連結、查詢狀態皆委派 StallPay。
"""
import httpx

from app.core.config import get_settings
from app.core.interfaces.payment_provider import (
    IPaymentProvider,
    PaymentRequest,
    PaymentResult,
)

settings = get_settings()


class StallPayProvider(IPaymentProvider):
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.stallpay_api_key}"}

    async def create_payment(self, request: PaymentRequest) -> PaymentResult:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.stallpay_api_base}/v1/payments",
                headers=self._headers(),
                json={
                    "tenant_id": request.tenant_id,
                    "order_id": request.order_id,
                    "amount": request.amount,        # 整數分位
                    "currency": request.currency,
                    "description": request.description,
                },
            )
            resp.raise_for_status()
            d = resp.json()
        return PaymentResult(
            provider="stallpay",
            reference=d.get("reference", ""),
            status=d.get("status", "pending"),
            redirect_url=d.get("redirect_url"),
        )

    async def get_status(self, reference: str) -> PaymentResult:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{settings.stallpay_api_base}/v1/payments/{reference}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            d = resp.json()
        return PaymentResult(
            provider="stallpay",
            reference=reference,
            status=d.get("status", "pending"),
            redirect_url=d.get("redirect_url"),
        )
