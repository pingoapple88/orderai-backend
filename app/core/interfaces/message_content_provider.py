"""IMessageContentProvider（律一：平台中立）：取得訊息附帶的媒體內容（圖片／語音）。

業務層只依賴本介面；LINE Messaging API 的 content endpoint 細節在 Adapter 內。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class MessageContent:
    data: bytes
    content_type: str


class MessageContentError(RuntimeError):
    """取媒體失敗的可稽核錯誤；業務層只依 reason_code 決定 fail-closed。"""

    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


class IMessageContentProvider(ABC):
    @abstractmethod
    async def get_message_content(self, message_id: str) -> MessageContent:
        """依訊息 id 取回媒體二進位與 content-type；失敗一律拋 MessageContentError。"""
