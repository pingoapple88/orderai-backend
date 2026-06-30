"""JWT 工具（律三）+ LINE Webhook 簽章驗證（PR-3 任務三）。"""
import base64
import hashlib
import hmac
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


def verify_line_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    """LINE Webhook 簽章驗證：HMAC-SHA256(channel_secret, raw_body) 經 base64 後比對。

    使用 hmac.compare_digest 防時序攻擊。channel_secret 缺漏時回 False（fail-closed）。
    """
    if not channel_secret or not signature:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)
