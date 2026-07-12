"""SQLAlchemy ORM 模型 — 對齊 migration 0004（Option A 租戶模型）。

0004 變更：
  - tenants → stores（租戶隔離邊界；新增 company_id / referred_by_dealer_id / plan / line_channel_id）
  - 新增 companies / dealers / customers（皆 INTEGER 自增 PK，FK 皆 Integer）
  - users.tenant_id → store_id，新增 picture_url（line_id 全域 UNIQUE 保留不動）
  - orders.tenant_id → store_id；total_amount → total_cents（值已是分，純改名）；
    新增 customer_id / ai_extraction(JSONB) / confirmed_at
  - order_items：unit_price → unit_price_cents、subtotal → subtotal_cents，新增 unit
  - 週邊表（user_preferences/billing_records/ai_extractions/ai_usage_logs/audit_logs）
    本期保留欄名 tenant_id，但 FK 目標改指向 stores.id（表已改名）。技術債登記在案。
  - 金額一律整數分（鐵律 7）；confidence_score 為機率值維持 Numeric(3,2)。
"""
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Company(Base):
    """多店老闆的集合層（可 NULL；單店老闆不需建）。"""
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Dealer(Base):
    """經銷商（推薦人）。※ 無 commission_rate，費率唯一來源在 merchcore-platform。"""
    __tablename__ = "dealers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # 推薦碼
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Store(Base):
    """租戶隔離邊界（原 tenants）。訂閱、額度、LINE channel 都掛這裡。"""
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    market: Mapped[str] = mapped_column(String(10), default="tw")  # tw/jp/th/us
    industry_type: Mapped[str] = mapped_column(String(20), default="ecom")  # PR-3
    company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companies.id"))
    referred_by_dealer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("dealers.id"))
    plan: Mapped[str] = mapped_column(Text, default="lite")
    line_channel_id: Mapped[Optional[str]] = mapped_column(Text)  # ※ secret 只在 Railway ENV，DB 不碰
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    monthly_price: Mapped[int] = mapped_column(Integer, nullable=False)  # 整數分位（已合規）
    currency: Mapped[str] = mapped_column(String(3), default="TWD")
    ai_extraction_limit: Mapped[Optional[int]] = mapped_column(Integer)
    team_member_limit: Mapped[Optional[int]] = mapped_column(Integer)
    features: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class Customer(Base):
    """店家的下單客戶（LINE 買家）。"""
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    line_user_id: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    line_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)  # 全域 UNIQUE 保留
    name: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    picture_url: Mapped[Optional[str]] = mapped_column(Text)  # 0004 新增
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)
    store_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("stores.id"))  # 原 tenant_id
    role: Mapped[str] = mapped_column(String(50), default="owner")
    ai_usage_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_usage_reset_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class UserPreference(Base):
    __tablename__ = "user_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("stores.id"))  # 欄名保留、FK→stores
    language: Mapped[str] = mapped_column(String(10), default="zh-TW")
    theme: Mapped[str] = mapped_column(String(10), default="light")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    line_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    store_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("stores.id"))  # 原 tenant_id
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("customers.id"))
    order_number: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255))
    customer_phone: Mapped[Optional[str]] = mapped_column(String(20))
    customer_email: Mapped[Optional[str]] = mapped_column(String(255))
    total_cents: Mapped[Optional[int]] = mapped_column(Integer)  # 原 total_amount（整數分）
    currency: Mapped[str] = mapped_column(String(3), default="TWD")
    status: Mapped[str] = mapped_column(String(50), default="pending_confirm")
    channel: Mapped[Optional[str]] = mapped_column(String(50))
    source_image_url: Mapped[Optional[str]] = mapped_column(Text)
    ai_extraction_id: Mapped[Optional[int]] = mapped_column(Integer)
    ai_extraction: Mapped[Optional[dict]] = mapped_column(JSONB)  # 0004 新增
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # 0004 新增
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    customer: Mapped[Optional["Customer"]] = relationship("Customer")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_name: Mapped[Optional[str]] = mapped_column(String(255))
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(Text, default="個")  # 0004 新增
    unit_price_cents: Mapped[Optional[int]] = mapped_column(Integer)  # 原 unit_price（整數分）
    subtotal_cents: Mapped[Optional[int]] = mapped_column(Integer)    # 原 subtotal（整數分）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    order: Mapped["Order"] = relationship(back_populates="items")


class BillingRecord(Base):
    __tablename__ = "billing_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("stores.id"))  # 欄名保留、FK→stores
    order_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL")
    )
    amount: Mapped[Optional[int]] = mapped_column(Integer)  # 整數分位
    currency: Mapped[str] = mapped_column(String(3), default="TWD")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    payment_method: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class AIExtraction(Base):
    __tablename__ = "ai_extractions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("stores.id"))  # 欄名保留、FK→stores
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    extraction_result: Mapped[Optional[dict]] = mapped_column(JSONB)
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))  # 機率值
    llm_provider: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("stores.id"))  # 欄名保留、FK→stores
    extraction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_extractions.id"))
    usage_date: Mapped[Optional[date]] = mapped_column(Date)
    usage_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("stores.id"))  # 欄名保留、FK→stores
    action: Mapped[Optional[str]] = mapped_column(String(255))
    resource_type: Mapped[Optional[str]] = mapped_column(String(50))
    resource_id: Mapped[Optional[int]] = mapped_column(Integer)
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class SystemSetting(Base):
    """PR-2：全域可調參數（禁止寫死於程式）。"""
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


__all__ = [
    "Company", "Dealer", "Store", "Plan", "Customer", "User", "UserPreference",
    "Order", "OrderItem", "BillingRecord", "AIExtraction", "AIUsageLog",
    "AuditLog", "SystemSetting",
]
