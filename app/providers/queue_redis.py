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

    def enqueue(self, payload: dict[str, Any]) -> None:
        # 將處理函式字串路徑交給 Worker，避免在 web 進程做重活。
        # ⚠️ 必須指向 sync 入口 run_worker：RQ 是同步 fork，不 await 協程；
        #    直接指向 async process_webhook_event 會被當普通函式呼叫、回傳未 await 的 coroutine（靜默 no-op）。
        self._q.enqueue("app.workers.line_worker.run_worker", payload)

    def depth(self) -> int:
        return len(self._q)
