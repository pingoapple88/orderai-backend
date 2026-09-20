"""Focused tests for the synthetic staging in-process P1 queue consumer."""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.providers.queue_memory import InMemoryQueue
from app.workers import p1_uat_memory_worker as worker


def _configure_allowed(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "p1_uat_memory_queue_worker_enabled", True)
    monkeypatch.setattr(worker.settings, "environment", "uat")
    monkeypatch.setattr(worker.settings, "railway_environment_name", "staging")
    monkeypatch.setattr(worker.settings, "p1_uat_environment_marker", "qingquan-p1-uat")
    monkeypatch.setattr(worker.settings, "p1_intake_enabled", True)
    monkeypatch.setattr(worker.settings, "queue_backend", "memory")
    monkeypatch.setattr(worker.settings, "p1_uat_memory_queue_poll_seconds", 0.05)


def test_uat_memory_worker_guard_is_fail_closed_outside_exact_scope(monkeypatch):
    _configure_allowed(monkeypatch)
    assert worker.is_p1_uat_memory_worker_allowed() is True

    monkeypatch.setattr(worker.settings, "railway_environment_name", "production")
    assert worker.is_p1_uat_memory_worker_allowed() is False

    monkeypatch.setattr(worker.settings, "railway_environment_name", "staging")
    monkeypatch.setattr(worker.settings, "queue_backend", "redis")
    assert worker.is_p1_uat_memory_worker_allowed() is False

    monkeypatch.setattr(worker.settings, "queue_backend", "memory")
    monkeypatch.setattr(worker.settings, "p1_uat_memory_queue_poll_seconds", 6.0)
    assert worker.is_p1_uat_memory_worker_allowed() is False


def test_uat_memory_worker_consumes_only_in_process_memory_payload(monkeypatch):
    _configure_allowed(monkeypatch)
    queue = InMemoryQueue()
    expected_payload = {"events": [{"webhookEventId": "synthetic-event"}]}
    queue.enqueue(expected_payload)
    observed = []
    stop_event = asyncio.Event()

    monkeypatch.setattr(worker, "get_queue", lambda: queue)

    async def _process(payload):
        observed.append(payload)
        stop_event.set()

    monkeypatch.setattr(worker.line_worker, "process_webhook_event", _process)

    asyncio.run(worker.run_p1_uat_memory_worker(stop_event))

    assert observed == [expected_payload]
    assert queue.depth() == 0


def test_uat_memory_worker_never_acquires_queue_when_guard_is_disabled(monkeypatch):
    _configure_allowed(monkeypatch)
    monkeypatch.setattr(worker.settings, "p1_uat_memory_queue_worker_enabled", False)

    def _unexpected_queue():
        raise AssertionError("disabled worker must not acquire queue")

    monkeypatch.setattr(worker, "get_queue", _unexpected_queue)
    asyncio.run(worker.run_p1_uat_memory_worker(asyncio.Event()))


def test_fastapi_lifecycle_starts_and_stops_only_the_guarded_uat_worker(monkeypatch):
    from app import main

    started = []
    stopped = []

    monkeypatch.setattr(worker, "is_p1_uat_memory_worker_allowed", lambda: True)

    async def _fake_worker(stop_event):
        started.append(True)
        await stop_event.wait()
        stopped.append(True)

    monkeypatch.setattr(worker, "run_p1_uat_memory_worker", _fake_worker)

    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
        assert started == [True]
        assert stopped == []

    assert stopped == [True]
