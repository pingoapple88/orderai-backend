# OrderAI 訂單解析規格 v1.0.0 (Adjudicated)
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from uuid import UUID, uuid4
from datetime import datetime

class OrderItemDraft(BaseModel):
    line_no: int
    raw_name: str
    qty: int
    item_confidence: float

class ParseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    redacted_text: str
    pii_redacted: bool = True

class OrderParseResult(BaseModel):
    schema_version: str = "1.0.0"
    company_id: UUID
    status: Literal["PENDING_REVIEW", "REJECTED"]
    confidence: float
    items: List[OrderItemDraft]
    metadata: ParseMetadata
    parsed_at: datetime = Field(default_factory=datetime.utcnow)
