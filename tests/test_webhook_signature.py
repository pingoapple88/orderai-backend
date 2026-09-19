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
from app.services import p1_intake_service


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


def test_unhandled_line_webhook_error_returns_generic_response_without_traceback(monkeypatch):
    """Unexpected P1 failures must not expose traceback, SQL, PII, or settings."""
    monkeypatch.setattr(webhook.settings, "line_messaging_channel_secret", "test-secret")
    monkeypatch.setattr(webhook.settings, "p1_intake_enabled", True)

    class _Session:
        def close(self):
            pass

    def _raise_sensitive_error(*_args, **_kwargs):
        raise RuntimeError("SELECT * FROM customers WHERE phone='0912345678'")

    monkeypatch.setattr(webhook, "SessionLocal", lambda: _Session())
    monkeypatch.setattr(p1_intake_service, "resolve_p1_store", lambda _db: object())
    monkeypatch.setattr(p1_intake_service, "record_line_events", _raise_sensitive_error)

    body = json.dumps({"destination": "Utest", "events": []}).encode()
    headers = {
        "X-Line-Signature": _make_signature(body, "test-secret"),
        "Content-Type": "application/json",
    }
    from app.main import app

    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/webhooks/line",
        content=body,
        headers=headers,
    )

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"},
    }
    assert "Traceback" not in response.text
    assert "SELECT" not in response.text
    assert "0912345678" not in response.text
