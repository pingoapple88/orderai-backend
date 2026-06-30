"""LINE OAuth + JWT（PR-2）。JWT 帶 user_id / tenant_id / role。"""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models import Plan, Tenant, User
from app.providers import get_auth_provider

router = APIRouter()
settings = get_settings()


@router.get("/line")
def line_login():
    state = secrets.token_urlsafe(8)
    return {"authorize_url": get_auth_provider().get_authorize_url(state)}


@router.get("/line/callback")
async def line_callback(code: Optional[str] = None, db: Session = Depends(get_db)):
    if not code:
        raise HTTPException(400, "Missing authorization code")
    profile = await get_auth_provider().exchange_code(code)

    user = db.execute(select(User).where(User.line_id == profile.external_id)).scalar_one_or_none()
    if user is None:
        # 新用戶：建立專屬租戶 + admin 角色 + 預設方案
        tenant = Tenant(name=profile.display_name or "New Tenant", market="tw")
        db.add(tenant)
        db.flush()
        default_plan = db.execute(select(Plan).order_by(Plan.monthly_price.asc())).scalars().first()
        user = User(line_id=profile.external_id, name=profile.display_name,
                    avatar_url=profile.avatar_url, plan_id=default_plan.id if default_plan else 1,
                    tenant_id=tenant.id, role="admin")
        db.add(user)
    else:
        user.name = profile.display_name or user.name
        user.avatar_url = profile.avatar_url or user.avatar_url
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "user_id": user.id, "tenant_id": user.tenant_id,
        "role": user.role, "line_user_id": profile.external_id, "provider": "line",
    })
    url = f"{settings.frontend_url}/api/auth/line/callback?token={token}&provider=line"
    return RedirectResponse(url)
