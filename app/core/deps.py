"""FastAPI 依賴：JWT 解析、目前 principal、角色守衛、租戶（store）隔離（律三）。"""
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
    # JWT 必含 user_id 與 store_id（0004 起租戶鍵為 store）
    if "user_id" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token")
    return payload


def verify_store_access(
    store_id: int, principal: dict = Depends(get_current_principal)
) -> dict:
    """路由帶 {store_id} 者必掛此依賴：JWT 的 store_id 必須等於 path store_id，否則 403。"""
    if principal.get("store_id") != store_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    return principal


def require_role(*roles: str):
    def _dep(principal: dict = Depends(get_current_principal)) -> dict:
        if principal.get("role") not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal
    return _dep
