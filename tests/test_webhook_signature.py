"""PR-3 任務三：LINE Webhook X-Line-Signature HMAC-SHA256 驗證測試。

純加密邏輯，不需 PG/Redis/LINE API，可完整單測。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import providers
from app.core.security import verify_line_signature
from app.providers.queue_memory import InMemoryQueue


def _make_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


# ── verify_line_signature 單元測試 ──────────────────────────────────────────

def test_valid_signature_returns_true():
    secret = "test-secret"
    body = b'{"events":[]}'
    sig = _make_signature(body, secret)
    assert verify_line_signature(body, sig, secret) is True


def test_wrong_signature_returns_false():
    assert verify_line_signature(b'{"events":[]}', "bad-sig", "test-secret") is False


def test_empty_secret_returns_false():
    body = b'{"events":[]}'
    sig = _make_signature(body, "test-secret")
    assert verify_line_signature(body, sig, "") is False


def test_empty_signature_returns_false():
    assert verify_line_signature(b'{"events":[]}', "", "test-secret") is False


# ── Webhook endpoint 整合測試 ───────────────────────────────────────────────

@pytest.fixture()
def client_with_queue(monkeypatch):
    """注入記憶體佇列 + 固定 channel_secret。"""
    from app.core import config as cfg_module

    monkeypatch.setattr(cfg_module.get_settings(), "line_channel_secret", "test-secret")

    q = InMemoryQueue()
    providers.set_queue(q)

    from app.main import app
    return TestClient(app), q


def test_valid_signature_enqueues_and_returns_200(client_with_queue):
    client, q = client_with_queue
    body = json.dumps({"events": [{"type": "message"}]}).encode()
    sig = _make_signature(body, "test-secret")
    resp = client.post(
        "/api/webhook/line",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert q.depth() == 1


def test_invalid_signature_returns_401_and_not_enqueued(client_with_queue):
    client, q = client_with_queue
    body = json.dumps({"events": []}).encode()
    resp = client.post(
        "/api/webhook/line",
        content=body,
        headers={"X-Line-Signature": "wrong-sig", "Content-Type": "application/json"},
    )
    assert resp.status_code == 401
    assert q.depth() == 0
