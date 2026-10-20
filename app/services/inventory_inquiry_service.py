"""M1-INV-01 人工庫存確認服務。

此模組只建立與人工確認庫存詢問；沒有 available-to-promise、庫存保留、扣庫、付款、
出貨或外部 ERP 呼叫。資訊不足或租戶範圍無法解析時一律 fail-closed。
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models import AuditLog, Customer, InventoryInquiry, Product, Store

INQUIRY_STATUSES = {"pending_review", "available", "unavailable"}
REVIEW_DECISIONS = {"available", "unavailable"}


class InquiryReferenceNotFound(Exception):
    """商品或客戶不在此門市範圍內。"""


class InquiryStateConflict(Exception):
    """詢問已被處理，不能重複確認。"""


def _resolve_company_id(db: Session, store_id: int) -> int:
    """只由已驗證的門市導出 company_id；無法導出時拒絕作業。"""
    store = db.get(Store, store_id)
    if store is None or store.company_id is None:
        raise PermissionError("tenant company_id unresolved; fail-closed")
    return store.company_id


def _audit(db: Session, principal: dict, action: str, inquiry_id: int,
           old: Optional[dict] = None, new: Optional[dict] = None) -> None:
    db.add(AuditLog(
        user_id=principal.get("user_id"),
        store_id=principal.get("store_id"),
        action=action,
        resource_type="inventory_inquiry",
        resource_id=inquiry_id,
        old_value=old,
        new_value=new,
    ))


def _get_scoped(db: Session, store_id: int, company_id: int,
                inquiry_id: int) -> Optional[InventoryInquiry]:
    return db.execute(
        select(InventoryInquiry)
        .join(Store, Store.id == InventoryInquiry.store_id)
        .where(
            InventoryInquiry.id == inquiry_id,
            InventoryInquiry.store_id == store_id,
            Store.company_id == company_id,
        )
    ).scalar_one_or_none()


def _verify_references(db: Session, store_id: int, product_id: Optional[int],
                       customer_id: Optional[int]) -> None:
    if product_id is not None:
        product = db.execute(
            select(Product.id).where(Product.id == product_id, Product.store_id == store_id)
        ).scalar_one_or_none()
        if product is None:
            raise InquiryReferenceNotFound("Product not found in store")
    if customer_id is not None:
        customer = db.execute(
            select(Customer.id).where(Customer.id == customer_id, Customer.store_id == store_id)
        ).scalar_one_or_none()
        if customer is None:
            raise InquiryReferenceNotFound("Customer not found in store")


def create_inquiry(db: Session, principal: dict, store_id: int, data: dict) -> InventoryInquiry:
    """建立待人工確認的詢問。建立本身不表示商品可供、也不會保留任何數量。"""
    company_id = _resolve_company_id(db, store_id)
    product_id = data.get("product_id")
    customer_id = data.get("customer_id")
    _verify_references(db, store_id, product_id, customer_id)

    inquiry = InventoryInquiry(
        store_id=store_id,
        product_id=product_id,
        customer_id=customer_id,
        requester_name=data.get("requester_name"),
        requested_product_name=data["requested_product_name"],
        requested_quantity=data.get("requested_quantity"),
        requested_unit=data.get("requested_unit"),
        status="pending_review",
    )
    db.add(inquiry)
    db.flush()
    _audit(
        db, principal, "inventory_inquiry.create", inquiry.id,
        new={
            "status": inquiry.status,
            "product_id": inquiry.product_id,
            "requested_product_name": inquiry.requested_product_name,
            "requested_quantity": inquiry.requested_quantity,
            "company_id": company_id,
            "reservation_created": False,
        },
    )
    db.commit()
    db.refresh(inquiry)
    event_bus.publish("inventory_inquiry.created", {"inquiry_id": inquiry.id, "store_id": store_id})
    return inquiry


def list_inquiries(db: Session, store_id: int, *, status: Optional[str] = None) -> list[InventoryInquiry]:
    company_id = _resolve_company_id(db, store_id)
    if status is not None and status not in INQUIRY_STATUSES:
        raise ValueError(f"invalid status: {status}")
    where = [InventoryInquiry.store_id == store_id, Store.company_id == company_id]
    if status is not None:
        where.append(InventoryInquiry.status == status)
    return db.execute(
        select(InventoryInquiry)
        .join(Store, Store.id == InventoryInquiry.store_id)
        .where(*where)
        .order_by(InventoryInquiry.created_at.desc())
    ).scalars().all()


def get_inquiry(db: Session, store_id: int, inquiry_id: int) -> Optional[InventoryInquiry]:
    company_id = _resolve_company_id(db, store_id)
    return _get_scoped(db, store_id, company_id, inquiry_id)


def review_inquiry(db: Session, principal: dict, store_id: int, inquiry_id: int,
                   decision: str, note: Optional[str] = None) -> Optional[InventoryInquiry]:
    """由人員回覆可供或不可供；結果不會建立保留、訂單或庫存異動。"""
    company_id = _resolve_company_id(db, store_id)
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"invalid decision: {decision}")
    inquiry = _get_scoped(db, store_id, company_id, inquiry_id)
    if inquiry is None:
        return None
    if inquiry.status != "pending_review":
        raise InquiryStateConflict("Inquiry has already been reviewed")

    old = {"status": inquiry.status, "decision_note": inquiry.decision_note}
    inquiry.status = decision
    inquiry.decision_note = note
    inquiry.reviewed_by_user_id = principal.get("user_id")
    inquiry.reviewed_at = datetime.now(timezone.utc)
    inquiry.updated_at = inquiry.reviewed_at
    _audit(
        db, principal, "inventory_inquiry.review", inquiry.id, old=old,
        new={
            "status": inquiry.status,
            "decision_note": inquiry.decision_note,
            "company_id": company_id,
            "reservation_created": False,
        },
    )
    db.commit()
    db.refresh(inquiry)
    event_bus.publish(
        "inventory_inquiry.reviewed",
        {"inquiry_id": inquiry.id, "store_id": store_id, "decision": decision},
    )
    return inquiry
