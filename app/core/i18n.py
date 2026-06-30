"""極簡 i18n（PR-2 骨架，支援 zh-TW / en）。"""
_MESSAGES = {
    "zh-TW": {
        "order_not_found": "找不到訂單",
        "ai_quota_exceeded": "本月 AI 解析次數已達上限，請升級或加購",
        "not_order_message": "非訂單訊息，已略過",
        "unauthorized": "未授權",
        "forbidden": "權限不足",
    },
    "en": {
        "order_not_found": "Order not found",
        "ai_quota_exceeded": "Monthly AI parsing limit reached; please upgrade",
        "not_order_message": "Not an order message; skipped",
        "unauthorized": "Unauthorized",
        "forbidden": "Forbidden",
    },
}


def t(key: str, lang: str = "zh-TW") -> str:
    return _MESSAGES.get(lang, _MESSAGES["zh-TW"]).get(key, key)
