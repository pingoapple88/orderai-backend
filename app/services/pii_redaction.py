"""LLM 與稽核共同使用的最小 PII 遮蔽器。"""
from __future__ import annotations

import re


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TW_PHONE = re.compile(r"(?<!\d)(?:\+?886[-\s]?)?0?9\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)")
_TW_ID = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][12]\d{8}(?!\d)")
_NAME_CONTEXT = re.compile(r"((?:我是|姓名|收件人|客戶|客人)\s*[：:]?\s*)[\u4e00-\u9fff]{2,4}")


def redact_pii(value: str | None) -> str:
    """保留商品／數量語意，遮蔽常見可識別欄位；不回傳原始值。"""
    text = value or ""
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    text = _TW_PHONE.sub("[REDACTED_PHONE]", text)
    text = _TW_ID.sub("[REDACTED_ID]", text)
    return _NAME_CONTEXT.sub(r"\1[REDACTED_NAME]", text)
