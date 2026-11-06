"""IMessageContentProvider 的 LINE 實作：GET /v2/bot/message/{id}/content（Messaging channel token）。

fail-closed：token 未設定、HTTP 失敗、逾時、超過大小上限 → MessageContentError（不重試、不猜）。
"""
from __future__ import annotations

import re

import httpx

from app.core.config import get_settings
from app.core.interfaces.message_content_provider import (
    IMessageContentProvider,
    MessageContent,
    MessageContentError,
)

_MESSAGE_ID = re.compile(r"^[0-9A-Za-z_-]{1,64}$")


class LineMessageContentProvider(IMessageContentProvider):
    CONTENT = "https://api-data.line.me/v2/bot/message/{message_id}/content"

    def __init__(self, *, access_token: str | None = None, max_bytes: int | None = None,
                 timeout_seconds: float | None = None) -> None:
        settings = get_settings()
        self.access_token = settings.line_messaging_access_token if access_token is None else access_token
        self.max_bytes = settings.line_content_max_bytes if max_bytes is None else max_bytes
        self.timeout_seconds = settings.line_content_timeout_seconds if timeout_seconds is None else timeout_seconds

    async def get_message_content(self, message_id: str) -> MessageContent:
        if not self.access_token:
            raise MessageContentError("media_token_not_configured")
        if not message_id or not _MESSAGE_ID.match(str(message_id)):
            raise MessageContentError("media_id_invalid")
        url = self.CONTENT.format(message_id=message_id)
        headers = {"Authorization": "Bearer {}".format(self.access_token)}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code != 200:
                        raise MessageContentError("media_fetch_failed", "status={}".format(resp.status_code))
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > self.max_bytes:
                        raise MessageContentError("media_too_large")
                    chunks = []
                    size = 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise MessageContentError("media_too_large")
                        chunks.append(chunk)
                    content_type = resp.headers.get("content-type", "application/octet-stream")
        except MessageContentError:
            raise
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise MessageContentError("media_fetch_timeout") from exc
        except httpx.HTTPError as exc:
            raise MessageContentError("media_fetch_failed") from exc
        data = b"".join(chunks)
        if not data:
            raise MessageContentError("media_empty")
        return MessageContent(data=data, content_type=content_type.split(";")[0].strip().lower())
