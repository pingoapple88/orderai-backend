"""RedisQueue：以 RQ 將 webhook 任務丟給背景 Worker（情境一）。"""
from typing import Any

from app.core.config import get_settings
from app.core.interfaces.queue import IQueue

settings = get_settings()


class RedisQueue(IQueue):
    def __init__(self) -> None:
        # 延遲匯入：未安裝 redis/rq 時，import 本模組不會失敗
        import redis
        from rq import Queue

        self._conn = redis.from_url(settings.redis_url)
        self._q = Queue(settings.queue_name, connection=self._conn)
        self._dead_letter_q = Queue("{}_dead_letter".format(settings.queue_name), connection=self._conn)

    def enqueue(self, payload: dict[str, Any]) -> None:
        # 將處理函式字串路徑交給 Worker，避免在 web 進程做重活。
        # ⚠️ 必須指向 sync 入口 run_worker：RQ 是同步 fork，不 await 協程；
        #    直接指向 async process_webhook_event 會被當普通函式呼叫、回傳未 await 的 coroutine（靜默 no-op）。
        self._q.enqueue("app.workers.line_worker.run_worker", payload)

    def enqueue_unique(self, payload: dict[str, Any], *, dedupe_key: str) -> bool:
        ttl = max(1, settings.queue_dedup_ttl_seconds)
        dedupe_name = "{}:dedupe:{}".format(settings.queue_name, dedupe_key)
        inserted = self._conn.set(dedupe_name, "1", nx=True, ex=ttl)
        if not inserted:
            return False
        self.enqueue(payload)
        return True

    def enqueue_retry(self, payload: dict[str, Any]) -> None:
        self.enqueue(payload)

    def dead_letter(self, payload: dict[str, Any], *, reason_code: str) -> None:
        self._dead_letter_q.enqueue(
            "app.workers.line_worker.run_dead_letter",
            {"payload": payload, "reason_code": reason_code},
        )

    def depth(self) -> int:
        return len(self._q)
