"""OrderAI 獨立服務與 MerchCore 模組能力端點。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.adapters.merchcore_module import OrderAIMerchCoreAdapter
from app.core.database import get_db
from app.core.deps import get_current_principal
from app.core.response import success_response
from app.schemas import ModulePlanOut, ModuleRegistrationCreate, ModuleRegistrationOut, ModuleStatusOut
from app.services import module_service


router = APIRouter()


@router.get("/orderai/health")
def module_health() -> dict:
    return {"status": "ok", "module_key": "orderai", "module_version": "1.8"}


@router.get("/orderai/manifest")
def module_manifest() -> dict:
    return success_response(OrderAIMerchCoreAdapter.module_manifest())


@router.get("/orderai/plans")
def module_plans(channel: str = Query(default="direct"), db: Session = Depends(get_db)) -> dict:
    plans = module_service.list_plans(db, channel=channel)
    return success_response(
        [ModulePlanOut.model_validate(plan).model_dump(by_alias=True) for plan in plans]
    )


@router.post("/orderai/registrations", status_code=201)
def create_registration(payload: ModuleRegistrationCreate, db: Session = Depends(get_db)) -> dict:
    registration = module_service.register_self_service(
        db,
        company_name=payload.company_name,
        store_name=payload.store_name,
        channel=payload.channel,
        locale=payload.locale,
        idempotency_key=payload.idempotency_key,
        plan_name=payload.plan_name,
    )
    return success_response(ModuleRegistrationOut.model_validate(registration).model_dump(by_alias=True))


@router.get("/orderai/status")
def module_status(
    principal: dict = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    status = module_service.get_module_status(db, principal=principal)
    return success_response(ModuleStatusOut.model_validate(status).model_dump(by_alias=True))
