"""M1-INV-01 人工庫存確認 API。

路徑固定為門市範圍，所有端點先驗證 JWT.store_id。此 API 不提供即時庫存、
庫存保留、扣庫、付款、出貨或外部服務呼叫。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import verify_store_access
from app.core.response import success_response
from app.schemas import InventoryInquiryCreate, InventoryInquiryOut, InventoryInquiryReview
from app.services import inventory_inquiry_service

router = APIRouter()


def _out(inquiry) -> dict:
    return InventoryInquiryOut.model_validate(inquiry).model_dump(by_alias=True)


@router.get("")
def list_inventory_inquiries(store_id: int, status: Optional[str] = None,
                             principal: dict = Depends(verify_store_access),
                             db: Session = Depends(get_db)):
    try:
        rows = inventory_inquiry_service.list_inquiries(db, store_id, status=status)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return success_response([_out(row) for row in rows])


@router.post("", status_code=201)
def create_inventory_inquiry(store_id: int, body: InventoryInquiryCreate,
                             principal: dict = Depends(verify_store_access),
                             db: Session = Depends(get_db)):
    try:
        inquiry = inventory_inquiry_service.create_inquiry(
            db, principal, store_id, body.model_dump(),
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except inventory_inquiry_service.InquiryReferenceNotFound as e:
        raise HTTPException(422, str(e))
    return success_response(_out(inquiry))


@router.get("/{inquiry_id}")
def get_inventory_inquiry(store_id: int, inquiry_id: int,
                          principal: dict = Depends(verify_store_access),
                          db: Session = Depends(get_db)):
    try:
        inquiry = inventory_inquiry_service.get_inquiry(db, store_id, inquiry_id)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    if inquiry is None:
        raise HTTPException(404, "Inventory inquiry not found")
    return success_response(_out(inquiry))


@router.post("/{inquiry_id}/review")
def review_inventory_inquiry(store_id: int, inquiry_id: int, body: InventoryInquiryReview,
                             principal: dict = Depends(verify_store_access),
                             db: Session = Depends(get_db)):
    try:
        inquiry = inventory_inquiry_service.review_inquiry(
            db, principal, store_id, inquiry_id, body.decision, body.note,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except inventory_inquiry_service.InquiryStateConflict as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if inquiry is None:
        raise HTTPException(404, "Inventory inquiry not found")
    return success_response(_out(inquiry))
