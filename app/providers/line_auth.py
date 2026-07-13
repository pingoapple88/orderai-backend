"""IAuthProvider + INotificationProvider 的 LINE 實作（律一：外部認證透過 Adapter）。

Task 4：兩支 channel 完全分離 —
  - OAuth（authorize / token 交換）用 LINE **Login** channel（line_login_*）
  - 推播 / reply 用 LINE **Messaging** channel（line_messaging_access_token）
混用會導致「每則訊息 401、錯誤訊息誤導」，故變數層嚴格分離。
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
            "client_id": settings.line_login_channel_id,
            "redirect_uri": settings.line_login_callback_url,
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
                    "redirect_uri": settings.line_login_callback_url,
                    "client_id": settings.line_login_channel_id,
                    "client_secret": settings.line_login_channel_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            # debug（暫時）：raise_for_status 不含 body，看不到 LINE 的錯誤原因。
            # 帶上 token_resp.text，LINE 會說明 invalid_client / redirect_uri mismatch 等。
            if token_resp.status_code != 200:
                raise RuntimeError(
                    f"LINE token exchange failed: {token_resp.status_code} {token_resp.text}"
                )
            access_token = token_resp.json()["access_token"]
            profile_resp = await client.get(
                self.PROFILE, headers={"Authorization": "Bearer {}".format(access_token)}
            )
            if profile_resp.status_code != 200:
                raise RuntimeError(
                    f"LINE profile fetch failed: {profile_resp.status_code} {profile_resp.text}"
                )
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
        """回覆或推播訊息（用 Messaging channel access token）。"""
        if not settings.line_messaging_access_token:
            raise RuntimeError("LINE_MESSAGING_ACCESS_TOKEN not configured")

        headers = {
            "Authorization": "Bearer {}".format(settings.line_messaging_access_token),
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
