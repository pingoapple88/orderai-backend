"""可替換訂閱狀態 Provider；不綁定支付或任何特定外部服務。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


SubscriptionTransition = Literal[
    "pending_payment",
    "active",
    "past_due",
    "canceled",
    "manual_review",
]


@dataclass(frozen=True)
class SubscriptionIntent:
    company_id: int
    store_id: int
    user_id: int
    plan_id: int
    channel: str
    idempotency_key: str


@dataclass(frozen=True)
class SubscriptionDecision:
    status: SubscriptionTransition
    effective_at: datetime
    reason_code: str | None = None


class ISubscriptionProvider(ABC):
    """純訂閱生命週期決策介面；付款與發票另由個別 Provider 處理。"""

    @abstractmethod
    def start(self, intent: SubscriptionIntent, *, now: datetime) -> SubscriptionDecision:
        """建立訂閱意向，預設不能直接啟用。"""

    @abstractmethod
    def transition(self, *, current_status: str, action: str, now: datetime) -> SubscriptionDecision:
        """驗證狀態轉換；未知 action 或狀態必須回傳 manual_review。"""
