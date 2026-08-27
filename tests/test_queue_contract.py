from app.providers.queue_memory import InMemoryQueue
from app.services.queue_payload import build_line_queue_envelope, with_retry_attempt
from app.workers.line_worker import WorkerEventOutcome, route_retryable_outcomes


def _safe_payload() -> dict:
    envelope = build_line_queue_envelope({
        "type": "message", "webhookEventId": "event-contract-001", "replyToken": "reply-token",
        "source": {"type": "user", "userId": "Ucontract"},
        "message": {"type": "text", "text": "姓名：王小姐 0912345678 email@example.com apple 2"},
    })
    assert envelope is not None
    return envelope[0]


def test_memory_queue_dedup_retry_and_dead_letter_contract(monkeypatch):
    queue = InMemoryQueue()
    payload = _safe_payload()
    key = payload["events"][0]["lineEventHash"]
    assert queue.enqueue_unique(payload, dedupe_key=key) is True
    assert queue.enqueue_unique(payload, dedupe_key=key) is False
    assert queue.depth() == 1

    monkeypatch.setattr("app.workers.line_worker.settings.queue_max_retries", 1)
    retryable = [WorkerEventOutcome("needs_review", "provider_timeout", retryable=True)]
    route_retryable_outcomes(payload, retryable, queue)
    retry = queue.pop()
    assert retry["events"][0]["queueMeta"] == {"attempt": 0}
    retry = queue.pop()
    assert retry["events"][0]["queueMeta"] == {"attempt": 1}

    route_retryable_outcomes(retry, retryable, queue)
    assert queue.depth() == 0
    assert queue.dead_letters[0]["reason_code"] == "provider_timeout"
    assert queue.dead_letters[0]["payload"]["events"][0]["queueMeta"] == {"attempt": 2}


def test_queue_envelope_and_retry_are_non_mutating_and_contain_no_raw_pii():
    payload = _safe_payload()
    original_text = payload["events"][0]["message"]["text"]
    assert "0912345678" not in original_text
    assert "王小姐" not in original_text
    assert "email@example.com" not in original_text
    assert "replyToken" not in payload["events"][0]
    retry = with_retry_attempt(payload, 1)
    assert payload["events"][0]["queueMeta"] == {"attempt": 0}
    assert retry["events"][0]["queueMeta"] == {"attempt": 1}
