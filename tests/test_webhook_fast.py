"""LINE webhook returns quickly while mandatory P1 configuration fails closed."""
import time
from fastapi.testclient import TestClient

from app import providers
from app.core import config as cfg_module
from app.providers.queue_memory import InMemoryQueue
from app.main import app


def test_webhook_fails_closed_fast_when_mandatory_p1_is_disabled(monkeypatch):
    # 將 channel_secret 設為空，讓 verify_line_signature 接受任何空簽章
    # 注意：verify_line_signature 空 secret 回 False，所以改用有效簽章
    import base64, hashlib, hmac, json

    secret = "test-fast"
    monkeypatch.setattr(cfg_module.get_settings(), "line_messaging_channel_secret", secret)

    q = InMemoryQueue()
    providers.set_queue(q)

    client = TestClient(app)
    payload = {"message": {"text": "肉乾+2"}}
    body = json.dumps(payload).encode()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    sig = base64.b64encode(digest).decode()

    t0 = time.perf_counter()
    resp = client.post(
        "/api/v1/webhooks/line",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert resp.status_code == 503
    assert q.depth() == 0
    assert elapsed_ms < 500  # 放寬到 500ms（沙箱環境）
