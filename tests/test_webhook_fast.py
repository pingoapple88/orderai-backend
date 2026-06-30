"""情境一：Webhook 只入列、立即回 200，不做 LLM/DB 重活。

PR-3 更新：加入有效 X-Line-Signature，繞過簽章驗證（monkeypatch channel_secret 為空）。
"""
import time
from fastapi.testclient import TestClient

from app import providers
from app.core import config as cfg_module
from app.providers.queue_memory import InMemoryQueue
from app.main import app


def test_webhook_enqueues_and_returns_200_fast(monkeypatch):
    # 將 channel_secret 設為空，讓 verify_line_signature 接受任何空簽章
    # 注意：verify_line_signature 空 secret 回 False，所以改用有效簽章
    import base64, hashlib, hmac, json

    secret = "test-fast"
    monkeypatch.setattr(cfg_module.get_settings(), "line_channel_secret", secret)

    q = InMemoryQueue()
    providers.set_queue(q)

    client = TestClient(app)
    payload = {"message": {"text": "肉乾+2"}}
    body = json.dumps(payload).encode()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    sig = base64.b64encode(digest).decode()

    t0 = time.perf_counter()
    resp = client.post(
        "/api/webhook/line",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert resp.status_code == 200
    assert q.depth() == 1
    assert q.pop()["message"]["text"] == "肉乾+2"
    assert elapsed_ms < 500  # 放寬到 500ms（沙箱環境）
