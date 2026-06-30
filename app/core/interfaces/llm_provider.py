"""ILLMProvider（集團守則：AI 服務可替換 OpenAI/Claude/Ollama）。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExtractedItem:
    product_name: str
    quantity: int
    unit_price: float


@dataclass
class ExtractionResult:
    items: list[ExtractedItem] = field(default_factory=list)
    customer_name: str | None = None
    customer_phone: str | None = None
    confidence_score: float = 0.0
    raw: dict = field(default_factory=dict)


class ILLMProvider(ABC):
    """LLM Adapter 介面。具體實作見 app/providers/。"""

    @abstractmethod
    async def extract_order(self, *, image_url: str | None = None, text: str | None = None) -> ExtractionResult:
        """從圖片或文字解析為結構化訂單。"""
