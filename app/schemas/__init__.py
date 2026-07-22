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


# ── 商品型錄（WO-006）─────────────────────────────────────────────────────────
class ProductOut(CamelModel):
    id: int
    store_id: int                       # → storeId
    name: str
    aliases: List[str] = []
    unit: str
    price_cents: int                    # → priceCents（律七：整數分）
    is_active: bool                     # → isActive
    created_at: Optional[datetime] = None   # → createdAt
    updated_at: Optional[datetime] = None   # → updatedAt


class ProductCreate(CamelModel):
    """POST 建立。price_cents 為 int → 非整數（如 45.5 / "abc"）Pydantic 自動 422（case #8）。"""
    name: str
    aliases: List[str] = []
    unit: str
    price_cents: int


class ProductUpdate(CamelModel):
    """PATCH 部分更新，欄位皆選填。price_cents 若給須為 int。"""
    name: Optional[str] = None
    aliases: Optional[List[str]] = None
    unit: Optional[str] = None
    price_cents: Optional[int] = None
    is_active: Optional[bool] = None


# ── 開團批次 / 貼上抄單（WO-009）─────────────────────────────────────────────
class BatchCreate(CamelModel):
    title: str


class BatchOut(CamelModel):
    id: int
    store_id: int                       # → storeId
    title: str
    status: str
    created_at: Optional[datetime] = None   # → createdAt
    closed_at: Optional[datetime] = None    # → closedAt


class ParseRequest(CamelModel):
    raw_text: str                       # ← rawText


class CommitLine(CamelModel):
    line_no: Optional[str] = None       # ← lineNo
    customer_name: Optional[str] = None
    product_name: Optional[str] = None
    product_id: Optional[int] = None
    qty: Optional[int] = None
    unit: Optional[str] = None
    unit_price_cents: Optional[int] = None  # ← unitPriceCents（null → 422 PRICE_REQUIRED）


class CommitRequest(CamelModel):
    raw_text: str                       # ← rawText（去重用）
    lines: List[CommitLine] = []
