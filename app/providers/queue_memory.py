"""InMemoryQueue：開發/測試用，不依賴 Redis。"""
from collections import deque
from typing import Any

from app.core.interfaces.queue import IQueue


class InMemoryQueue(IQueue):
    def __init__(self) -> None:
        self._dq: deque[dict[str, Any]] = deque()

    def enqueue(self, payload: dict[str, Any]) -> None:
        self._dq.append(payload)

    def depth(self) -> int:
        return len(self._dq)

    # 測試輔助
    def pop(self) -> dict[str, Any]:
        return self._dq.popleft()
