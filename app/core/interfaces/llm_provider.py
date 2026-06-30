"""ILLMProvider（集團守則：AI 服務可替換）。PR-3：加入 industry_type 與美業欄位。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ExtractedItem:
    # 統一結構：ecom 用 product_name/quantity/unit_price；
    # beauty 將 service_name 映射到 product_name，並帶 appointment_time / staff_name。
    product_name: str
    quantity: int = 1
    unit_price: int = 0
    appointment_time: Optional[str] = None   # beauty
    staff_name: Optional[str] = None          # beauty


@dataclass
class ExtractionResult:
    items: List[ExtractedItem] = field(default_factory=list)
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    confidence_score: float = 0.0
    industry_type: str = "ecom"
    raw: Dict = field(default_factory=dict)


class ILLMProvider(ABC):
    @abstractmethod
    async def extract_order(
        self,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        industry_type: str = "ecom",
    ) -> ExtractionResult:
        """從圖片或文字解析為結構化訂單，依 industry_type 切換解析範本。"""
