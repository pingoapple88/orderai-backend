"""ILLMProvider（集團守則：AI 服務可替換 OpenAI/Claude/Ollama）。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


from typing import Optional
@dataclass
class ExtractedItem:
    product_name: str
    quantity: int
    unit_price: float


@dataclass
class ExtractionResult:
    items: list[ExtractedItem] = field(default_factory=list)
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    confidence_score: float = 0.0
    raw: dict = field(default_factory=dict)


class ILLMProvider(ABC):
    """LLM Adapter 介面。具體實作見 app/providers/。"""

    @abstractmethod
    async def extract_order(self, *, image_url: Optional[str] = None, text: Optional[str] = None) -> ExtractionResult:
        """從圖片或文字解析為結構化訂單。"""
