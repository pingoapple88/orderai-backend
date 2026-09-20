"""P1 隔離 staging 的 memory queue 消費者。

僅為沒有 Redis worker 的合成 UAT 環境提供同一個 FastAPI process 內的受控消費者。
所有條件必須精確成立；production、非 UAT、非 memory queue 或任一設定缺失時一律不啟動。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import get_settings
from app.providers import get_queue
from app.providers.queue_memory import InMemoryQueue
from app.workers import line_worker

logger = logging.getLogger(__name__)
settings = get_settings()

_UAT_ENVIRONMENT = "uat"
_UAT_MARKER = "qingquan-p1-uat"
_STAGING_ENVIRONMENT = "staging"
_MIN_POLL_SECONDS = 0.05
_MAX_POLL_SECONDS = 5.0


def is_p1_uat_memory_worker_allowed() -> bool:
    """Return true only for the explicitly enabled synthetic staging worker."""
    return (
        settings.p1_uat_memory_queue_worker_enabled
        and settings.environment.strip().lower() == _UAT_ENVIRONMENT
        and settings.railway_environment_name.strip().lower() == _STAGING_ENVIRONMENT
        and settings.p1_uat_environment_marker == _UAT_MARKER
        and settings.p1_intake_enabled
        and settings.queue_backend.strip().lower() == "memory"
        and _MIN_POLL_SECONDS <= settings.p1_uat_memory_queue_poll_seconds <= _MAX_POLL_SECONDS
    )


async def run_p1_uat_memory_worker(stop_event: asyncio.Event) -> None:
    """Consume only the in-process synthetic UAT queue until shutdown.

    A payload never leaves the process or enters logs. Line worker failures remain
    fail-closed in the event ledger and do not create formal transactions.
    """
    if not is_p1_uat_memory_worker_allowed():
        logger.info("P1 UAT memory worker disabled by environment guard")
        return

    queue = get_queue()
    if not isinstance(queue, InMemoryQueue):
        logger.error("P1 UAT memory worker blocked: queue implementation mismatch")
        return

    logger.info("P1 UAT memory worker started")
    while not stop_event.is_set():
        try:
            payload: dict[str, Any] = queue.pop()
        except IndexError:
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.p1_uat_memory_queue_poll_seconds
                )
            except TimeoutError:
                continue
            continue

        try:
            await line_worker.process_webhook_event(payload)
        except Exception:  # noqa: BLE001 - processing is retained fail-closed in its own ledger path.
            logger.error("P1 UAT memory worker event processing failed closed")

    logger.info("P1 UAT memory worker stopped")
