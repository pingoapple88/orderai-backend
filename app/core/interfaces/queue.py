"""IQueue（情境一：Webhook 非同步解耦的佇列抽象）。"""
from abc import ABC, abstractmethod
from typing import Any


class IQueue(ABC):
    @abstractmethod
    def enqueue(self, payload: dict[str, Any]) -> None:
        """將已去識別化的最小 payload 入列；必須極快、非阻塞。"""

    @abstractmethod
    def enqueue_unique(self, payload: dict[str, Any], *, dedupe_key: str) -> bool:
        """僅首次投遞相同事件；回傳本次是否確實入列。"""

    @abstractmethod
    def enqueue_retry(self, payload: dict[str, Any]) -> None:
        """將已增加 retry metadata 的既有安全 payload 重新入列。"""

    @abstractmethod
    def dead_letter(self, payload: dict[str, Any], *, reason_code: str) -> None:
        """將超過有限重試的安全 payload 轉入人工確認佇列。"""

    @abstractmethod
    def depth(self) -> int:
        """目前佇列深度（SuperAdmin 監控用）。"""
