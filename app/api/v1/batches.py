"""開團批次 + 貼上抄單 + 統計 API（WO-009）。掛載於 /api/v1/stores/{store_id}/batches。

沿用既有 store-scoped + verify_store_access（跨店 403）、envelope、camelCase、泛用 code。
紅線：parse 只回草稿不寫庫；parse/commit 分離；不引入任何 LINE 推播。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import verify_store_access
from app.core.response import success_response
from app.models import Store
from app.providers import get_llm_provider
from app.schemas import BatchCreate, BatchOut, CommitRequest, ParseRequest
from app.services import batch_service

router = APIRouter()


def _batch_out(b) -> dict:
    return BatchOut(
        id=b.id, store_id=b.store_id, title=b.title, status=b.status,
        created_at=b.created_at, closed_at=b.closed_at,
    ).model_dump(by_alias=True)


def _require_batch(db: Session, store_id: int, batch_id: int):
    b = batch_service.get_batch(db, store_id, batch_id)
    if not b:
        raise HTTPException(404, "Batch not found")   # 本店範圍內查無 → 404
    return b


@router.post("", status_code=201)
def create_batch(store_id: int, body: BatchCreate,
                 principal: dict = Depends(verify_store_access),
                 db: Session = Depends(get_db)):
    b = batch_service.create_batch(db, principal, store_id, body.title)
    return success_response(_batch_out(b))


@router.get("")
def list_batches(store_id: int, status: Optional[str] = None,
                 principal: dict = Depends(verify_store_access),
                 db: Session = Depends(get_db)):
    rows = batch_service.list_batches(db, store_id, status=status)
    return success_response([_batch_out(b) for b in rows])


@router.post("/{batch_id}/close")
def close_batch(store_id: int, batch_id: int,
                principal: dict = Depends(verify_store_access),
                db: Session = Depends(get_db)):
    _require_batch(db, store_id, batch_id)
    try:
        b = batch_service.close_batch(db, principal, store_id, batch_id)
    except batch_service.DuplicateCommit:
        raise HTTPException(409, "Batch already closed")
    return success_response(_batch_out(b))


@router.post("/{batch_id}/parse")
async def parse_batch(store_id: int, batch_id: int, body: ParseRequest,
                      principal: dict = Depends(verify_store_access),
                      db: Session = Depends(get_db)):
    b = _require_batch(db, store_id, batch_id)
    store = db.get(Store, store_id)
    industry = (store.industry_type if store else None) or "ecom"
    try:
        draft = await batch_service.parse_batch(
            db, store_id, b, body.raw_text, get_llm_provider(), industry_type=industry
        )
    except batch_service.BatchClosed:
        raise HTTPException(409, "Batch is closed")
    return success_response(draft)


@router.post("/{batch_id}/commit", status_code=201)
def commit_batch(store_id: int, batch_id: int, body: CommitRequest,
                 principal: dict = Depends(verify_store_access),
                 db: Session = Depends(get_db)):
    b = _require_batch(db, store_id, batch_id)
    lines = [ln.model_dump(by_alias=True) for ln in body.lines]  # camelCase 鍵，對齊 service 讀取
    try:
        res = batch_service.commit_batch(db, principal, store_id, b, body.raw_text, lines)
    except batch_service.BatchClosed:
        raise HTTPException(409, "Batch is closed")
    except batch_service.DuplicateCommit:
        raise HTTPException(409, "Duplicate commit")
    except batch_service.PriceRequired as e:
        # 422：回出缺價的 line_no（沿用泛用 VALIDATION_ERROR，detail 帶 lineNos）
        raise HTTPException(422, {"message": "Price required", "lineNos": e.line_nos})
    return success_response(res)


@router.get("/{batch_id}/summary")
def batch_summary(store_id: int, batch_id: int,
                  principal: dict = Depends(verify_store_access),
                  db: Session = Depends(get_db)):
    b = _require_batch(db, store_id, batch_id)
    return success_response(batch_service.summary(db, store_id, b))
