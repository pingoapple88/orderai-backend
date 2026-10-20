"""LLM 與 audit 共用的最小 PII 遮蔽器。"""
from __future__ import annotations

import re


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TW_PHONE = re.compile(r"(?<!\d)(?:\+?886[-\s]?)?0?9\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)")
_INTL_PHONE = re.compile(r"(?<!\d)\+?\d{1,3}[-\s]?\d{2,4}[-\s]?\d{3,4}[-\s]?\d{3,4}(?!\d)")
_TW_ID = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][12]\d{8}(?!\d)")
_CN_NAME = re.compile(r"((?:我是|姓名|收件人|客戶|客人)\s*[：:]?\s*)[\u4e00-\u9fff]{2,4}")
_EN_NAME = re.compile(r"\b((?:my name is|name|customer)\s*[:=]?\s*)[A-Za-z][A-Za-z .'-]{1,60}", re.IGNORECASE)
_TH_NAME = re.compile(r"((?:(?:ช[ื่ิ]+อ)|ชื่อ|ลูกค้า)\s*[：:]?\s*)[ก-๙\s]{2,80}?(?=\s+(?:โทร|อีเมล)|$)")
_JA_NAME = re.compile(r"((?:氏名|名前|お名前|お客さま)\s*[：:]?\s*)[\u3040-\u30ff\u4e00-\u9fff]{2,80}")
_ID_NAME = re.compile(r"\b((?:nama|pelanggan)\s*[:=]?\s*)[A-Za-z][A-Za-z .'-]{1,60}", re.IGNORECASE)


def redact_pii(value: str | None) -> str:
    """保留商品／數量語意，遮蔽五語系常見可識別欄位；不回傳原始值。"""
    text = value or ""
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    text = _TW_PHONE.sub("[REDACTED_PHONE]", text)
    text = _INTL_PHONE.sub("[REDACTED_PHONE]", text)
    text = _TW_ID.sub("[REDACTED_ID]", text)
    for pattern in (_CN_NAME, _EN_NAME, _TH_NAME, _JA_NAME, _ID_NAME):
        text = pattern.sub(r"\1[REDACTED_NAME]", text)
    return text
