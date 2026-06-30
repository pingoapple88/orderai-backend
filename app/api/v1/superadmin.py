"""SuperAdmin API（PR-2）：僅 role='superadmin' 可存取。

- 改 plans 定價/額度
- 改 system_settings 全域參數
- 監控：queue 深度 + AI 使用量
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models import AIUsageLog, Plan, SystemSetting
from app.providers import get_queue

router = APIRouter(dependencies=[Depends(require_role("superadmin"))])


@router.put("/plans/{plan_id}")
def update_plan(plan_id: int, body: dict, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    for f in ("monthly_price", "ai_extraction_limit", "team_member_limit"):
        if f in body and body[f] is not None:
            setattr(plan, f, int(body[f]))
    db.commit()
    return {"id": plan.id, "monthly_price": plan.monthly_price,
            "ai_extraction_limit": plan.ai_extraction_limit}


@router.put("/settings/{key}")
def update_setting(key: str, body: dict, db: Session = Depends(get_db)):
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key)
        db.add(row)
    row.value = str(body.get("value"))
    if body.get("description") is not None:
        row.description = body["description"]
    db.commit()
    return {"key": row.key, "value": row.value}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    first_of_month = date.today().replace(day=1)
    ai_usage = db.execute(
        select(func.coalesce(func.sum(AIUsageLog.usage_count), 0))
        .where(AIUsageLog.usage_date >= first_of_month)
    ).scalar_one()
    try:
        depth = get_queue().depth()
    except Exception:
        depth = -1  # Redis 不可用時不讓監控端點崩潰
    return {"queue_depth": depth, "ai_usage_this_month": int(ai_usage)}
