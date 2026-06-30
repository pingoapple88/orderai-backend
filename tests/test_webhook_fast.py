"""情境一：Webhook 只入列、立即回 200，不做 LLM/DB 重活。"""
import time
from fastapi.testclient import TestClient

from app import providers
from app.providers.queue_memory import InMemoryQueue
from app.main import app


def test_webhook_enqueues_and_returns_200_fast():
    q = InMemoryQueue()
    providers.set_queue(q)            # 注入記憶體佇列，繞過 Redis
    client = TestClient(app)

    t0 = time.perf_counter()
    resp = client.post("/api/webhook/line", json={"message": {"text": "肉乾+2"}})
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert resp.status_code == 200
    assert q.depth() == 1                       # 已入列
    assert q.pop()["message"]["text"] == "肉乾+2"
    assert elapsed_ms < 100                      # 快速回應（情境一要求）
