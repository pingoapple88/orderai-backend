"""訂單 API（契約 P0 #4-7）。掛載於 /api/v1/stores/{store_id}/orders。

每一支都掛 verify_store_access（JWT.store_id == path store_id，否則 403），
每一條 query 都經 order_service 強制 WHERE store_id。回應走統一信封 {success,data}。
"""
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import verify_store_access
from app.core.response import success_response
from app.models import Order
from app.schemas import CustomerOut, OrderDetailOut, OrderItemOut, OrderListItemOut
from app.services import order_service

router = APIRouter()


def _detail_dict(order: Order) -> dict:
    data = OrderDetailOut(
        id=order.id,
        order_number=order.order_number,
        store_id=order.store_id,
        customer=(
            CustomerOut(
                id=order.customer.id,
                name=order.customer.name,
                line_user_id=order.customer.line_user_id,
            )
            if order.customer is not None
            else None
        ),
        items=[
            OrderItemOut(
                id=i.id, name=i.product_name, quantity=i.quantity, unit=i.unit,
                unit_price_cents=i.unit_price_cents, subtotal_cents=i.subtotal_cents,
            )
            for i in order.items
        ],
        total_cents=order.total_cents,
        status=order.status,
        created_at=order.created_at,
        confirmed_at=order.confirmed_at,
    ).model_dump(by_alias=True)
    # aiExtraction：原樣回傳已結構化的 JSONB（可能為 None）
    data["aiExtraction"] = order.ai_extraction
    return data


@router.get("")
def list_orders(store_id: int, page: int = 1, limit: int = 20,
                status: Optional[str] = None,
                principal: dict = Depends(verify_store_access),
                db: Session = Depends(get_db)):
    rows, total = order_service.list_orders(db, store_id, page=page, limit=limit, status=status)
    data = [
        OrderListItemOut(
            id=r.id, order_number=r.order_number, total_cents=r.total_cents,
            status=r.status, created_at=r.created_at,
        ).model_dump(by_alias=True)
        for r in rows
    ]
    pagination = {
        "page": page, "pageSize": limit, "total": total,
        "totalPages": ceil(total / limit) if limit else 0,
    }
    return success_response(data, pagination=pagination)


@router.get("/{order_id}")
def get_order(store_id: int, order_id: int,
              principal: dict = Depends(verify_store_access),
              db: Session = Depends(get_db)):
    order = order_service.get_order(db, store_id, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return success_response(_detail_dict(order))


@router.post("/{order_id}/confirm")
def confirm_order(store_id: int, order_id: int,
                  principal: dict = Depends(verify_store_access),
                  db: Session = Depends(get_db)):
    order = order_service.confirm_order(db, principal, store_id, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return success_response(_detail_dict(order))


@router.put("/{order_id}")
def update_order(store_id: int, order_id: int, body: dict,
                 principal: dict = Depends(verify_store_access),
                 db: Session = Depends(get_db)):
    try:
        order = order_service.update_order(db, principal, store_id, order_id, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not order:
        raise HTTPException(404, "Order not found")
    return success_response(_detail_dict(order))
