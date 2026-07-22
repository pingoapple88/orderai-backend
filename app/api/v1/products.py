"""商品型錄 API（WO-006）。掛載於 /api/v1/stores/{store_id}/products。

沿用既有 pattern（裁決）：store-scoped 路徑 + verify_store_access（跨店 403）、
統一信封 {success,data}、camelCase、七個泛用 code（重複品名 → 409 CONFLICT）。
契約 §2.2 的裸 items / snake_case / 404 / 語意錯誤碼一律以既有為準、契約改。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import verify_store_access
from app.core.response import success_response
from app.schemas import ProductCreate, ProductOut, ProductUpdate
from app.services import product_service

router = APIRouter()


def _out(p) -> dict:
    return ProductOut(
        id=p.id, store_id=p.store_id, name=p.name, aliases=p.aliases or [],
        unit=p.unit, price_cents=p.price_cents, is_active=p.is_active,
        created_at=p.created_at, updated_at=p.updated_at,
    ).model_dump(by_alias=True)


@router.get("")
def list_products(store_id: int, is_active: Optional[bool] = None,
                  principal: dict = Depends(verify_store_access),
                  db: Session = Depends(get_db)):
    rows = product_service.list_products(db, store_id, is_active=is_active)
    return success_response([_out(p) for p in rows])


@router.post("", status_code=201)
def create_product(store_id: int, body: ProductCreate,
                   principal: dict = Depends(verify_store_access),
                   db: Session = Depends(get_db)):
    try:
        p = product_service.create_product(db, principal, store_id, body.model_dump())
    except product_service.ProductNameDuplicate:
        raise HTTPException(409, "Product name already exists")
    return success_response(_out(p))


@router.patch("/{product_id}")
def update_product(store_id: int, product_id: int, body: ProductUpdate,
                   principal: dict = Depends(verify_store_access),
                   db: Session = Depends(get_db)):
    try:
        p = product_service.update_product(
            db, principal, store_id, product_id,
            body.model_dump(exclude_unset=True),
        )
    except product_service.ProductNameDuplicate:
        raise HTTPException(409, "Product name already exists")
    if not p:
        raise HTTPException(404, "Product not found")
    return success_response(_out(p))


@router.delete("/{product_id}", status_code=204)
def delete_product(store_id: int, product_id: int,
                   principal: dict = Depends(verify_store_access),
                   db: Session = Depends(get_db)):
    ok = product_service.soft_delete_product(db, principal, store_id, product_id)
    if not ok:
        raise HTTPException(404, "Product not found")
    return Response(status_code=204)
