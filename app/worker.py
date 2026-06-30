"""背景 Worker（情境一）：消化 LINE webhook 佇列。

正式以 RQ 啟動：`rq worker line_webhook`，或執行本檔的簡易輪詢迴圈。
process_webhook_event 為 RQ enqueue 的目標函式。
"""
import time

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.ai_service import is_order_message

settings = get_settings()


def process_webhook_event(payload: dict) -> None:
    """單筆 webhook 事件處理：pre-filter → (PR-3 接 LLM 解析建單)。"""
    text = (payload.get("message") or {}).get("text", "")
    db = SessionLocal()
    try:
        if not is_order_message(db, text):
            return  # 情境二：非訂單訊息，不呼叫 LLM、不扣額
        # TODO(PR-3)：呼叫 ILLMProvider 解析 → 建單 → 扣 ai_usage_logs
    finally:
        db.close()


def main() -> None:
    """以 RQ Worker 啟動（容器 entrypoint）。"""
    import redis
    from rq import Queue, Worker

    conn = redis.from_url(settings.redis_url)
    worker = Worker([Queue(settings.queue_name, connection=conn)], connection=conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
