"""可替換發票狀態 Provider；OrderAI 不直接整合特定發票供應商。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


InvoiceStatus = Literal["pending", "issued", "manual_review", "void"]


@dataclass(frozen=True)
class InvoiceRequest:
    company_id: int
    store_id: int
    user_id: int
    subscription_id: int
    amount_minor: int
    currency: str
    idempotency_key: str


@dataclass(frozen=True)
class InvoiceResult:
    status: InvoiceStatus
    reference: str | None = None
    reason_code: str | None = None


class IInvoiceProvider(ABC):
    """發票僅能經此介面申請；unknown 不得視為已開立。"""

    @abstractmethod
    def issue(self, request: InvoiceRequest) -> InvoiceResult:
        """建立發票請求或轉人工審閱。"""
