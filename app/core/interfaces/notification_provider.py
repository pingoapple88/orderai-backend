"""INotificationProvider（鐵律1）：發訊抽象，與認證分離。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class INotificationProvider(ABC):
    @abstractmethod
    async def send_message(self, *, to: str, text: str, reply_token: Optional[str] = None) -> None:
        """回覆/推播訊息給使用者（LINE reply 或 push）。"""
