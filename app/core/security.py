"""JWT 工具（律三：驗權基礎）。"""
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings

settings = get_settings()


def create_access_token(payload: dict) -> str:
    """簽發 JWT。payload 應含整數 userId（對齊 users.id）。"""
    to_encode = payload.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """驗證並解碼 JWT；失敗丟出 jwt 例外，由呼叫端轉 401。"""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
