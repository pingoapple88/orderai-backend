"""IErpIngestProvider — 雲鼎 ERP 入站待確認訂單 Adapter 介面（律一）。

WO-04 ENG-03 契約層：僅定義介面與 fail-closed 錯誤。
在雲鼎 owner 提供 sandbox + 書面契約前，一律走 BlockedErpIngestProvider
（app/providers/erp_blocked.py）—— 不連線、不硬編 endpoint、不送任何資料（WO-04 §4）。
金額一律整數分位（律七）。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


class ErpIngestBlockedError(RuntimeError):
    """ERP 連線/契約未就緒時的 fail-closed 錯誤（WO-04 §4）。"""

    def __init__(self, reason_code: str = "ERP_CONNECTION_BLOCKED", message: str = ""):
        super().__init__(message or reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ErpIngestItem:
    resolved_sku: Optional[str]        # 比不到型錄為 None（律七不逼填）
    quantity: int
    unit_price_minor: Optional[int]    # 整數分位；未定價 None
    price_source: str                  # CATALOG / UNPRICED


@dataclass(frozen=True)
class ErpIngestRequest:
    company_id: int                    # 租戶隔離鍵（律三）
    order_id: int
    idempotency_key: str               # 律三：重送去重
    currency: str                      # ISO-4217
    currency_exponent: int             # TWD = 0
    items: List[ErpIngestItem]


@dataclass(frozen=True)
class ErpIngestResult:
    provider: str
    reference: str
    status: str                        # accepted / rejected


class IErpIngestProvider(ABC):
    """雲鼎 ERP 待確認訂單入站 Adapter。具體實作見 app/providers/。"""

    @abstractmethod
    async def submit_pending_order(self, request: ErpIngestRequest) -> ErpIngestResult:
        """送出一張待確認訂單至雲鼎 ERP。未就緒時 raise ErpIngestBlockedError。"""
