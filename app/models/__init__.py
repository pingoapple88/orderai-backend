from typing import Optional
"""SQLAlchemy ORM 模型 — 對應 schema.sql 的 10 張表（PR-1b）。

PR-1b 變更：
  - 金額欄位改 Integer（整數分位，鐵律 7）：plans.monthly_price、orders.total_amount、
    order_items.unit_price、order_items.subtotal、billing_records.amount。
  - 新增 Tenant 模型；users 加 tenant_id / role；各業務表加 tenant_id（鐵律 3）。
  - confidence_score 為機率值，維持 Numeric(3,2)。
型別嚴格對齊 schema.sql（DDL 唯一真實來源）。
"""
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


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    market: Mapped[str] = mapped_column(String(10), default="tw")  # tw/jp/th/us
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    # PR-3：產業類型，控制 LLM Prompt 切換（ecom/beauty/food）
    industry_type: Mapped[str] = mapped_column(String(20), default="ecom")


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    monthly_price: Mapped[int] = mapped_column(Integer, nullable=False)  # 整數分位
    currency: Mapped[str] = mapped_column(String(3), default="TWD")
    ai_extraction_limit: Mapped[Optional[int]] = mapped_column(Integer)
    team_member_limit: Mapped[Optional[int]] = mapped_column(Integer)
    features: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    line_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id"))  # PR-1b
    role: Mapped[str] = mapped_column(String(50), default="admin")                    # PR-1b
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
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id"))  # PR-1b
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
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id"))  # PR-1b
    order_number: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255))
    customer_phone: Mapped[Optional[str]] = mapped_column(String(20))
    customer_email: Mapped[Optional[str]] = mapped_column(String(255))
    total_amount: Mapped[Optional[int]] = mapped_column(Integer)  # 整數分位
    currency: Mapped[str] = mapped_column(String(3), default="TWD")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    channel: Mapped[Optional[str]] = mapped_column(String(50))
    source_image_url: Mapped[Optional[str]] = mapped_column(Text)
    ai_extraction_id: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_name: Mapped[Optional[str]] = mapped_column(String(255))
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    unit_price: Mapped[Optional[int]] = mapped_column(Integer)  # 整數分位
    subtotal: Mapped[Optional[int]] = mapped_column(Integer)    # 整數分位
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    order: Mapped["Order"] = relationship(back_populates="items")


class BillingRecord(Base):
    __tablename__ = "billing_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id"))  # PR-1b
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
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id"))  # PR-1b
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
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id"))  # PR-1b
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
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id"))  # PR-1b
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
    "Tenant", "Plan", "User", "UserPreference", "Order", "OrderItem",
    "BillingRecord", "AIExtraction", "AIUsageLog", "AuditLog", "SystemSetting",
]
