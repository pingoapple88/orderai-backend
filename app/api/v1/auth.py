"""LINE OAuth + JWT（Task 4）。JWT 帶 user_id / store_id / role。

OAuth 用 LINE **Login** channel（line_login_*）。callback URL 由 settings 提供。
users.line_id 全域 UNIQUE 保留，scalar_one_or_none() 安全，登入邏輯不改查詢方式。
"""
from typing import Optional
import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_principal
from app.core.response import success_response
from app.core.security import create_access_token
from app.models import Plan, Store, User
from app.providers import get_auth_provider
from app.schemas import MeOut, MeStoreOut, MeUserOut

router = APIRouter()
settings = get_settings()


@router.get("/line/login")
def line_login():
    # 前端直接 window.location.href 開這支端點 → 必須 302 導向，不能回 JSON。
    # state 存 httponly cookie，callback 比對，補上原本缺席的 CSRF 防護。
    state = secrets.token_urlsafe(16)
    url = get_auth_provider().get_authorize_url(state)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(
        "line_oauth_state", state,
        max_age=600, httponly=True, secure=True, samesite="lax", path="/api/v1/auth",
    )
    return resp


@router.get("/line/callback")
async def line_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    line_oauth_state: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if not code:
        raise HTTPException(400, "Missing authorization code")
    # CSRF：state 必須存在且與 login 時種下的 cookie 相符（compare_digest 防時序），fail-closed。
    if not state or not line_oauth_state or not secrets.compare_digest(state, line_oauth_state):
        raise HTTPException(400, "Invalid state")
    profile = await get_auth_provider().exchange_code(code)

    user = db.execute(select(User).where(User.line_id == profile.external_id)).scalar_one_or_none()
    if user is None:
        # 新用戶：建立專屬 store + owner 角色 + 預設方案
        store = Store(name=profile.display_name or "New Store", market="tw")
        db.add(store)
        db.flush()
        default_plan = db.execute(select(Plan).order_by(Plan.monthly_price.asc())).scalars().first()
        user = User(
            line_id=profile.external_id,
            name=profile.display_name,
            avatar_url=profile.avatar_url,
            picture_url=profile.avatar_url,
            plan_id=default_plan.id if default_plan else 1,
            store_id=store.id,
            role="owner",
        )
        db.add(user)
    else:
        user.name = profile.display_name or user.name
        user.avatar_url = profile.avatar_url or user.avatar_url
        user.picture_url = profile.avatar_url or user.picture_url
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "user_id": user.id, "store_id": user.store_id,
        "role": user.role, "line_user_id": profile.external_id, "provider": "line",
    })
    url = f"{settings.frontend_url}/auth/callback?token={token}&provider=line"
    resp = RedirectResponse(url)
    resp.delete_cookie("line_oauth_state", path="/api/v1/auth")
    return resp


@router.get("/me")
def me(principal: dict = Depends(get_current_principal), db: Session = Depends(get_db)):
    user = db.get(User, principal["user_id"])
    if user is None:
        raise HTTPException(404, "User not found")
    store = db.get(Store, user.store_id) if user.store_id else None
    data = MeOut(
        user=MeUserOut(
            id=user.id, name=user.name, role=user.role,
            picture_url=user.picture_url or user.avatar_url,
        ),
        store=MeStoreOut(
            id=store.id if store else 0,
            name=store.name if store else None,
            company_id=store.company_id if store else None,
            plan=store.plan if store else None,
        ),
    ).model_dump(by_alias=True)
    return success_response(data)
