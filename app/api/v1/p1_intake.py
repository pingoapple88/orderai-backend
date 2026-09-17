"""青泉谷 P1 人工覆核與受控隔離送件 API。"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role, verify_store_access
from app.core.response import success_response
from app.schemas import P1IntakeCaseOut, P1IntakeDispatchOut, P1IntakeReview
from app.services import p1_delivery_service

router = APIRouter()


def _case_out(case) -> dict:
    return P1IntakeCaseOut.model_validate(case).model_dump(by_alias=True)


@router.get("")
def list_p1_cases(
    store_id: int,
    state: Optional[str] = None,
    principal: dict = Depends(verify_store_access),
    db: Session = Depends(get_db),
):
    try:
        return success_response([_case_out(row) for row in p1_delivery_service.list_cases(db, store_id, state)])
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/{conversation_id}/review")
def review_p1_case(
    store_id: int,
    conversation_id: int,
    body: P1IntakeReview,
    principal: dict = Depends(require_role("owner", "manager")),
    db: Session = Depends(get_db),
):
    if principal.get("store_id") != store_id:
        raise HTTPException(403, "Store access denied")
    try:
        case = p1_delivery_service.review_case(
            db, principal, store_id, conversation_id,
            customer_confirmed=body.customer_confirmed, note=body.note,
        )
        return success_response(_case_out(case))
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except p1_delivery_service.P1ConversationNotFound:
        raise HTTPException(404, "P1 intake case not found")
    except p1_delivery_service.P1StateConflict as exc:
        raise HTTPException(409, str(exc))
    except p1_delivery_service.P1DeliveryBlocked as exc:
        raise HTTPException(422, exc.reason_code)


@router.post("/{conversation_id}/dispatch")
async def dispatch_p1_case(
    store_id: int,
    conversation_id: int,
    principal: dict = Depends(require_role("owner", "manager")),
    db: Session = Depends(get_db),
):
    if principal.get("store_id") != store_id:
        raise HTTPException(403, "Store access denied")
    try:
        outbox = await p1_delivery_service.dispatch_outbox(db, principal, store_id, conversation_id)
        return success_response(P1IntakeDispatchOut.model_validate(outbox).model_dump(by_alias=True))
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except p1_delivery_service.P1ConversationNotFound:
        raise HTTPException(404, "P1 intake case not found")
    except p1_delivery_service.P1StateConflict as exc:
        raise HTTPException(409, str(exc))
    except p1_delivery_service.P1DeliveryBlocked as exc:
        raise HTTPException(422, exc.reason_code)
