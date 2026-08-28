"""本機 deterministic 訂閱／發票 Provider，僅供合成測試與 Demo injection。"""
from __future__ import annotations

from datetime import datetime

from app.core.interfaces.invoice_provider import IInvoiceProvider, InvoiceRequest, InvoiceResult
from app.core.interfaces.subscription_provider import ISubscriptionProvider, SubscriptionDecision, SubscriptionIntent


class LocalSubscriptionProvider(ISubscriptionProvider):
    """沒有外連的訂閱轉換守衛；所有不明轉換一律人工審閱。"""

    def start(self, intent: SubscriptionIntent, *, now: datetime) -> SubscriptionDecision:
        return SubscriptionDecision(status="pending_payment", effective_at=now)

    def transition(self, *, current_status: str, action: str, now: datetime) -> SubscriptionDecision:
        transitions = {
            ("pending_payment", "payment_confirmed"): "active",
            ("pending_payment", "mark_past_due"): "past_due",
            ("active", "mark_past_due"): "past_due",
            ("active", "renew"): "pending_payment",
            ("active", "change_plan"): "pending_payment",
            ("active", "cancel"): "canceled",
            ("past_due", "cancel"): "canceled",
            ("past_due", "renew"): "pending_payment",
        }
        status = transitions.get((current_status, action))
        if status is None:
            return SubscriptionDecision(status="manual_review", effective_at=now, reason_code="UNKNOWN_TRANSITION")
        return SubscriptionDecision(status=status, effective_at=now)


class LocalManualReviewInvoiceProvider(IInvoiceProvider):
    """無正式發票連線時固定轉人工，永不偽裝成 issued。"""

    def issue(self, request: InvoiceRequest) -> InvoiceResult:
        return InvoiceResult(status="manual_review", reason_code="INVOICE_PROVIDER_NOT_CONFIGURED")
