"""InMemoryQueue：開發/測試用，不依賴 Redis。"""
from collections import deque
from typing import Any

from app.core.interfaces.queue import IQueue


class InMemoryQueue(IQueue):
    def __init__(self) -> None:
        self._dq: deque[dict[str, Any]] = deque()
        self._dedupe_keys: set[str] = set()
        self.dead_letters: list[dict[str, Any]] = []

    def enqueue(self, payload: dict[str, Any]) -> None:
        self._dq.append(payload)

    def enqueue_unique(self, payload: dict[str, Any], *, dedupe_key: str) -> bool:
        if dedupe_key in self._dedupe_keys:
            return False
        self._dedupe_keys.add(dedupe_key)
        self.enqueue(payload)
        return True

    def enqueue_retry(self, payload: dict[str, Any]) -> None:
        self.enqueue(payload)

    def dead_letter(self, payload: dict[str, Any], *, reason_code: str) -> None:
        self.dead_letters.append({"payload": payload, "reason_code": reason_code})

    def depth(self) -> int:
        return len(self._dq)

    # 測試輔助
    def pop(self) -> dict[str, Any]:
        return self._dq.popleft()
