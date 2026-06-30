"""IAuthProvider 的 LINE 實作（律一：外部認證透過 Adapter）。

PR-1 僅提供骨架與授權 URL；完整 token 交換在 PR-2 實作。
"""
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.interfaces.auth_provider import AuthProfile, IAuthProvider

settings = get_settings()


class LineAuthProvider(IAuthProvider):
    AUTHORIZE = "https://access.line.me/oauth2/v2.1/authorize"
    TOKEN = "https://api.line.me/oauth2/v2.1/token"
    PROFILE = "https://api.line.me/v2/profile"

    def get_authorize_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.line_channel_id,
            "redirect_uri": f"{settings.frontend_url}/api/auth/line/callback",
            "state": state,
            "scope": "profile openid",
        }
        return f"{self.AUTHORIZE}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> AuthProfile:
        async with httpx.AsyncClient(timeout=30) as client:
            token_resp = await client.post(
                self.TOKEN,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": f"{settings.frontend_url}/api/auth/line/callback",
                    "client_id": settings.line_channel_id,
                    "client_secret": settings.line_channel_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            profile_resp = await client.get(
                self.PROFILE, headers={"Authorization": f"Bearer {access_token}"}
            )
            profile_resp.raise_for_status()
            p = profile_resp.json()

        return AuthProfile(
            provider="line",
            external_id=p["userId"],
            display_name=p.get("displayName"),
            avatar_url=p.get("pictureUrl"),
        )
