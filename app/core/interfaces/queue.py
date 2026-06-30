"""IQueue（情境一：Webhook 非同步解耦的佇列抽象）。"""
from abc import ABC, abstractmethod
from typing import Any


class IQueue(ABC):
    @abstractmethod
    def enqueue(self, payload: dict[str, Any]) -> None:
        """將 raw payload 入列；必須極快、非阻塞。"""

    @abstractmethod
    def depth(self) -> int:
        """目前佇列深度（SuperAdmin 監控用）。"""
