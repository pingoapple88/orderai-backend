# orderai-backend: app/schemas/erp_order.py (P0#1 雲鼎 ERP 入站契約)
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime
from uuid import UUID

class ErpOrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_no: int
    resolved_sku: Optional[str] = None    # 比不到 → None, 不逼填
    qty: str                              # 數量使用十進位字串，避免浮點數誤差 (如 "3.75" 斤)
    unit_price_minor: Optional[int] = None # 型錄帶入，非 LLM; UNPRICED → None
    price_source: Literal["CATALOG", "UNPRICED"]

class ErpOrderIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: int                       # 對齊現行 INTEGER (BigInt)
    order_id: str                         # 外部訂單編號 (如 LINE Event ID)
    idempotency_key: str                  # 律三：確保重複發送不產生二筆
    currency: str = "TWD"                 # ISO-4217
    currency_exponent: int = 0            # TWD 指數為 0
    items: List[ErpOrderItem]
    status: Literal["pending_confirm", "confirmed", "cancelled"]
    occurred_at: datetime                 # UTC 時間
    parsed_at: datetime = Field(default_factory=datetime.utcnow)
