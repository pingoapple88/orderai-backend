"""FastAPI 依賴：JWT 解析、目前使用者、角色守衛（律三）。"""
import jwt
from fastapi import Depends, Header, HTTPException, status

from app.core.security import decode_access_token


def get_current_principal(authorization: str = Header(default="")) -> dict:
    scheme, _, token = authorization.partition(" ")
    if scheme != "Bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    # 需含整數 user_id 與 tenant_id（PR-1b/PR-2）
    if "user_id" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token")
    return payload


def require_role(*roles: str):
    def _dep(principal: dict = Depends(get_current_principal)) -> dict:
        if principal.get("role") not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal
    return _dep
