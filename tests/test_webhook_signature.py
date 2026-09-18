"""LINE webhook signature and mandatory P1 intake gate tests."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import providers
from app.api.v1 import webhook
from app.core.security import verify_line_signature
from app.providers.queue_memory import InMemoryQueue


def _make_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def test_valid_signature_returns_true():
    secret = "test-secret"
    body = b'{"events":[]}'
    assert verify_line_signature(body, _make_signature(body, secret), secret) is True


def test_wrong_signature_returns_false():
    assert verify_line_signature(b'{"events":[]}', "bad-sig", "test-secret") is False


def test_empty_secret_returns_false():
    body = b'{"events":[]}'
    assert verify_line_signature(body, _make_signature(body, "test-secret"), "") is False


def test_empty_signature_returns_false():
    assert verify_line_signature(b'{"events":[]}', "", "test-secret") is False


@pytest.fixture()
def client_with_queue(monkeypatch):
    """Inject an in-memory queue and only the signing credential."""
    monkeypatch.setattr(webhook.settings, "line_messaging_channel_secret", "test-secret")
    monkeypatch.setattr(webhook.settings, "p1_intake_enabled", False)
    queue = InMemoryQueue()
    providers.set_queue(queue)
    from app.main import app

    return TestClient(app), queue


def test_valid_signature_without_p1_configuration_fails_closed_and_is_not_enqueued(client_with_queue):
    client, queue = client_with_queue
    body = json.dumps({"events": [{"type": "message"}]}).encode()
    response = client.post(
        "/api/v1/webhooks/line",
        content=body,
        headers={"X-Line-Signature": _make_signature(body, "test-secret"), "Content-Type": "application/json"},
    )
    assert response.status_code == 503
    assert queue.depth() == 0


def test_invalid_signature_returns_401_and_not_enqueued(client_with_queue):
    client, queue = client_with_queue
    body = json.dumps({"events": []}).encode()
    response = client.post(
        "/api/v1/webhooks/line",
        content=body,
        headers={"X-Line-Signature": "wrong-sig", "Content-Type": "application/json"},
    )
    assert response.status_code == 401
    assert queue.depth() == 0
