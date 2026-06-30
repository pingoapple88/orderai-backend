"""IPaymentProvider 的 StallPay 實作（骨架）。

PR-1b：僅佔位。實際 StallPay API 呼叫於 PR-2 補完。
OrderAI 本身不碰金流，所有支付委派至此 Adapter。
"""
from app.core.interfaces.payment_provider import (
    IPaymentProvider,
    PaymentRequest,
    PaymentResult,
)


class StallPayProvider(IPaymentProvider):
    async def create_payment(self, request: PaymentRequest) -> PaymentResult:
        raise NotImplementedError("StallPay create_payment 待 PR-2 實作")

    async def get_status(self, reference: str) -> PaymentResult:
        raise NotImplementedError("StallPay get_status 待 PR-2 實作")
