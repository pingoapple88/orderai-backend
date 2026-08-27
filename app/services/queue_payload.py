"""Webhook Queue envelope 的最小化、去識別化與 retry metadata 工具。"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Optional

from app.services.pii_redaction import redact_pii


def _stable_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def build_line_queue_envelope(event: Any) -> Optional[tuple[dict[str, Any], str]]:
    """只輸出 Worker 所需、可再識別性較低的單事件 payload。"""
    if not isinstance(event, dict):
        return None
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    event_id = event.get("webhookEventId")
    text = message.get("text") if message.get("type") == "text" else None
    safe_event: dict[str, Any] = {
        "type": event.get("type") if isinstance(event.get("type"), str) else "unknown",
        "source": {"type": source.get("type") if isinstance(source.get("type"), str) else "unknown"},
        "message": {"type": message.get("type") if isinstance(message.get("type"), str) else "unknown"},
        "queueMeta": {"attempt": 0},
    }
    if isinstance(text, str):
        safe_event["message"]["text"] = redact_pii(text)
    if isinstance(event_id, str) and event_id:
        safe_event["lineEventHash"] = _stable_hash(event_id)
        dedupe_key = safe_event["lineEventHash"]
    else:
        dedupe_key = _stable_hash(json.dumps(safe_event, ensure_ascii=False, sort_keys=True))
    user_id = source.get("userId")
    if isinstance(user_id, str) and user_id:
        safe_event["source"]["lineUserHash"] = _stable_hash(user_id)
    return {"events": [safe_event]}, dedupe_key


def with_retry_attempt(payload: dict[str, Any], attempt: int) -> dict[str, Any]:
    """不可原地修改已入列 payload，避免 memory queue 測試與 adapter 共用資料被污染。"""
    next_payload = deepcopy(payload)
    for event in next_payload.get("events", []):
        if isinstance(event, dict):
            metadata = event.get("queueMeta") if isinstance(event.get("queueMeta"), dict) else {}
            metadata["attempt"] = attempt
            event["queueMeta"] = metadata
    return next_payload
