"""訂單 API（PR-2）。所有操作經 order_service，帶 tenant_id + user_id 隔離。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_principal
from app.core.i18n import t
from app.services import order_service

router = APIRouter()


@router.post("", status_code=201)
def create_order(body: dict, principal: dict = Depends(get_current_principal),
                 db: Session = Depends(get_db)):
    if not body.get("items"):
        raise HTTPException(400, "items required")
    o = order_service.create_order(db, principal, body)
    return {"id": o.id, "order_number": o.order_number, "status": o.status,
            "total_amount": o.total_amount, "currency": o.currency}


@router.get("")
def list_orders(page: int = 1, limit: int = 20, status: str | None = None,
                principal: dict = Depends(get_current_principal), db: Session = Depends(get_db)):
    rows, total = order_service.list_orders(db, principal, page=page, limit=limit, status=status)
    return {"orders": [{"id": r.id, "order_number": r.order_number, "status": r.status,
                        "total_amount": r.total_amount} for r in rows],
            "pagination": {"page": page, "limit": limit, "total": total}}


@router.get("/{order_id}")
def get_order(order_id: int, principal: dict = Depends(get_current_principal),
              db: Session = Depends(get_db)):
    o = order_service.get_order(db, principal, order_id)
    if not o:
        raise HTTPException(404, t("order_not_found", principal.get("lang", "zh-TW")))
    return {"id": o.id, "order_number": o.order_number, "status": o.status,
            "total_amount": o.total_amount,
            "items": [{"product_name": i.product_name, "quantity": i.quantity,
                       "unit_price": i.unit_price, "subtotal": i.subtotal} for i in o.items]}


@router.put("/{order_id}")
def update_order(order_id: int, body: dict, principal: dict = Depends(get_current_principal),
                 db: Session = Depends(get_db)):
    o = order_service.update_order(db, principal, order_id, body)
    if not o:
        raise HTTPException(404, t("order_not_found", principal.get("lang", "zh-TW")))
    return {"id": o.id, "status": o.status}
