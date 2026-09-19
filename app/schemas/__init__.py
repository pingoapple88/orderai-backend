"""Pydantic 回應 schema（API 契約 v1.0 §三）。

命名一致性鐵律：DB/Python/JWT/URL path 用 snake_case；API JSON body 用 camelCase。
轉換一律由此處的 CamelModel（alias_generator=to_camel + populate_by_name）完成，
路由端以欄位名建構、輸出時 model_dump(by_alias=True)。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
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


# ── 人工庫存確認（M1-INV-01）──────────────────────────────────────────────────
class InventoryInquiryCreate(CamelModel):
    requester_name: Optional[str] = Field(default=None, max_length=120)
    customer_id: Optional[int] = Field(default=None, ge=1)
    product_id: Optional[int] = Field(default=None, ge=1)
    requested_product_name: str = Field(min_length=1, max_length=255)
    requested_quantity: Optional[int] = Field(default=None, ge=1)
    requested_unit: Optional[str] = Field(default=None, max_length=30)


class InventoryInquiryReview(CamelModel):
    decision: Literal["available", "unavailable"]
    note: Optional[str] = Field(default=None, max_length=1000)


class InventoryInquiryOut(CamelModel):
    id: int
    store_id: int
    product_id: Optional[int] = None
    customer_id: Optional[int] = None
    requester_name: Optional[str] = None
    requested_product_name: str
    requested_quantity: Optional[int] = None
    requested_unit: Optional[str] = None
    status: str
    decision_note: Optional[str] = None
    reviewed_by_user_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── 青泉谷 P1 人工覆核／隔離送件 ──────────────────────────────────────────────
class P1IntakeReview(CamelModel):
    customer_confirmed: bool
    note: Optional[str] = Field(default=None, max_length=1000)


class P1IntakeCaseOut(CamelModel):
    id: int
    store_id: int
    state: str
    state_version: int
    reason_codes: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class P1InboundEventOut(CamelModel):
    """Safe operational metadata for a non-terminal signed inbound event."""
    id: int
    store_id: int
    webhook_event_id: str
    event_type: str
    message_type: Optional[str] = None
    status: str
    error_code: Optional[str] = None
    occurred_at: Optional[datetime] = None
    claimed_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class P1IntakeDispatchOut(CamelModel):
    id: int
    conversation_id: int
    status: str
    attempt_count: int
    last_error_code: Optional[str] = None
    updated_at: Optional[datetime] = None


class P1ReadinessChecksOut(CamelModel):
    """Boolean-only P1 prerequisite results; no configuration values are exposed."""
    intake_enabled: bool
    store_company_scope_resolved: bool
    encryption_key_valid: bool
    identity_hmac_key_valid: bool
    queue_provider_available: bool
    erp_delivery_blocked: bool


class P1UnresolvedEventCountsOut(CamelModel):
    """Aggregate-only operational workload, constrained to the authorized scope."""
    queued: int
    processing: int
    failed: int


class P1ReadinessOut(CamelModel):
    """Safe, store-scoped P1 readiness result without PII or deployment details."""
    ready: bool
    checks: P1ReadinessChecksOut
    unresolved_event_counts: P1UnresolvedEventCountsOut
    stale_processing_count: int
    has_stale_processing: bool
    reason_codes: List[str] = []


# ── 開團批次 / 貼上抄單（WO-009）──────────────────────────────────────────────────
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


# ── W2 Module self-service ──────────────────────────────────────────────────
class ModuleRegistrationCreate(CamelModel):
    company_name: str = Field(min_length=1, max_length=120)
    store_name: str = Field(min_length=1, max_length=120)
    channel: Literal["direct", "dealer", "enterprise"]
    locale: Literal["zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"] = "zh-Hant-TW"
    idempotency_key: str = Field(min_length=8, max_length=255, pattern=r"^[A-Za-z0-9._:-]+$")
    plan_name: Optional[str] = Field(default=None, min_length=1, max_length=100)


class ModulePlanOut(CamelModel):
    name: str
    channel: str
    monthly_price: int
    currency: str
    ai_extraction_limit: Optional[int] = None
    team_member_limit: Optional[int] = None
    price_version_date: str = "2026-08-24"
    price_disclaimer: str = "以官網最新價格為準"


class ModuleRegistrationOut(CamelModel):
    id: int
    module_key: str
    module_version: str
    channel: str
    locale: str
    status: str


class ModuleStatusOut(CamelModel):
    store_key: Optional[str] = None
    plan_name: Optional[str] = None
    channel: Optional[str] = None
    ai_usage_count: int
    ai_extraction_limit: Optional[int] = None
    status: str
