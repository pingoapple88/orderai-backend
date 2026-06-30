"""律五：事件驅動。Phase 1 提供 in-process 同步 EventBus。

未來可替換為 Redis/Kafka 等實作而不動呼叫端。
"""
from collections import defaultdict
from collections.abc import Callable
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[dict[str, Any]], None]]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable[[dict[str, Any]], None]) -> None:
        self._handlers[event].append(handler)

    def publish(self, event: str, payload: dict[str, Any]) -> None:
        for handler in self._handlers.get(event, []):
            handler(payload)


# 模組級單例（Phase 1）
event_bus = EventBus()
