"""IAuthProvider + INotificationProvider 的 LINE 實作（律一：外部認證透過 Adapter）。

PR-3：LineAuthProvider 同時實作 INotificationProvider（send_message），
      發訊與認證分離（INotificationProvider 獨立介面），LINE 同時實作兩者。
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.interfaces.auth_provider import AuthProfile, IAuthProvider
from app.core.interfaces.notification_provider import INotificationProvider

settings = get_settings()


class LineAuthProvider(IAuthProvider, INotificationProvider):
    AUTHORIZE = "https://access.line.me/oauth2/v2.1/authorize"
    TOKEN = "https://api.line.me/oauth2/v2.1/token"
    PROFILE = "https://api.line.me/v2/profile"
    REPLY = "https://api.line.me/v2/bot/message/reply"
    PUSH = "https://api.line.me/v2/bot/message/push"

    def get_authorize_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.line_channel_id,
            "redirect_uri": "{}/api/auth/line/callback".format(settings.frontend_url),
            "state": state,
            "scope": "profile openid",
        }
        return "{}?{}".format(self.AUTHORIZE, urlencode(params))

    async def exchange_code(self, code: str) -> AuthProfile:
        async with httpx.AsyncClient(timeout=30) as client:
            token_resp = await client.post(
                self.TOKEN,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": "{}/api/auth/line/callback".format(settings.frontend_url),
                    "client_id": settings.line_channel_id,
                    "client_secret": settings.line_channel_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]
            profile_resp = await client.get(
                self.PROFILE, headers={"Authorization": "Bearer {}".format(access_token)}
            )
            profile_resp.raise_for_status()
            p = profile_resp.json()
        return AuthProfile(
            provider="line",
            external_id=p["userId"],
            display_name=p.get("displayName"),
            avatar_url=p.get("pictureUrl"),
        )

    async def send_message(
        self, *, to: str, text: str, reply_token: Optional[str] = None
    ) -> None:
        """回覆或推播訊息。有 reply_token 時用 reply API（免費），否則用 push API。"""
        if not settings.line_channel_access_token:
            raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN not configured")

        headers = {
            "Authorization": "Bearer {}".format(settings.line_channel_access_token),
            "Content-Type": "application/json",
        }
        messages = [{"type": "text", "text": text}]

        async with httpx.AsyncClient(timeout=30) as client:
            if reply_token:
                await client.post(
                    self.REPLY,
                    headers=headers,
                    json={"replyToken": reply_token, "messages": messages},
                )
            else:
                await client.post(
                    self.PUSH,
                    headers=headers,
                    json={"to": to, "messages": messages},
                )
