"""IPaymentProvider（集團守則：OrderAI 不直接處理金流，委派 StallPay）。

PR-1b 僅定義介面；具體 StallPay 實作於 PR-2 補完。
金額一律以整數分位（最小幣別單位）傳遞。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PaymentRequest:
    tenant_id: int
    order_id: int
    amount: int          # 整數分位
    currency: str        # TWD / JPY / THB / USD
    description: Optional[str] = None


@dataclass
class PaymentResult:
    provider: str
    reference: str       # StallPay 交易參照
    status: str          # pending / paid / failed
    redirect_url: Optional[str] = None


class IPaymentProvider(ABC):
    """支付 Adapter 介面。具體實作見 app/providers/stallpay.py。"""

    @abstractmethod
    async def create_payment(self, request: PaymentRequest) -> PaymentResult:
        """建立一筆支付（委派給 StallPay）。"""

    @abstractmethod
    async def get_status(self, reference: str) -> PaymentResult:
        """查詢支付狀態。"""
