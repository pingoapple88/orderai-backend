"""Pydantic 回應 schema（API 契約 v1.0 §三）。

命名一致性鐵律：DB/Python/JWT/URL path 用 snake_case；API JSON body 用 camelCase。
轉換一律由此處的 CamelModel（alias_generator=to_camel + populate_by_name）完成，
路由端以欄位名建構、輸出時 model_dump(by_alias=True)。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# ── /auth/me ────────────────────────────────────────────────────────────────
class MeUserOut(CamelModel):
    id: int
    name: Optional[str] = None
    role: Optional[str] = None
    picture_url: Optional[str] = None  # → pictureUrl


class MeStoreOut(CamelModel):
    id: int
    name: Optional[str] = None
    company_id: Optional[int] = None  # → companyId
    plan: Optional[str] = None


class MeOut(CamelModel):
    user: MeUserOut
    store: MeStoreOut


# ── 訂單 ─────────────────────────────────────────────────────────────────────
class OrderItemOut(CamelModel):
    id: int
    name: Optional[str] = None          # 來源 order_items.product_name
    quantity: Optional[int] = None
    unit: Optional[str] = None
    unit_price_cents: Optional[int] = None  # → unitPriceCents
    subtotal_cents: Optional[int] = None    # → subtotalCents


class CustomerOut(CamelModel):
    id: int
    name: Optional[str] = None
    line_user_id: Optional[str] = None  # → lineUserId


class OrderListItemOut(CamelModel):
    id: int
    order_number: Optional[str] = None  # → orderNumber
    total_cents: Optional[int] = None   # → totalCents
    status: str
    created_at: Optional[datetime] = None  # → createdAt


class OrderDetailOut(CamelModel):
    id: int
    order_number: Optional[str] = None
    store_id: Optional[int] = None
    customer: Optional[CustomerOut] = None
    items: List[OrderItemOut] = []
    total_cents: Optional[int] = None
    status: str
    created_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None  # → confirmedAt
    # aiExtraction 由路由端直接附加（原樣回傳已結構化的 JSONB）
