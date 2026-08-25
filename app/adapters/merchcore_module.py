"""OrderAI 對 MerchCore 的模組能力與事件 Adapter。"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
from typing import Any
from uuid import uuid4


SUPPORTED_LOCALES = ("zh-TW", "en", "th", "ja", "id")
MODULE_KEY = "orderai"
MODULE_VERSION = "1.8"

_DISPLAY_NAMES = {
    "zh-TW": "OrderAI 訂單解析服務",
    "en": "OrderAI Order Parsing Service",
    "th": "บริการวิเคราะห์คำสั่งซื้อ OrderAI",
    "ja": "OrderAI 注文解析サービス",
    "id": "Layanan Analisis Pesanan OrderAI",
}


def normalize_locale(locale: str | None) -> str:
    return locale if locale in SUPPORTED_LOCALES else "zh-TW"


class OrderAIMerchCoreAdapter:
    """只提供描述與簽名事件，不連線或耦合其他模組資料庫。"""

    @staticmethod
    def module_manifest(event_types: tuple[str, ...] = ()) -> dict[str, Any]:
        return {
            "module_key": MODULE_KEY,
            "module_version": MODULE_VERSION,
            "display_name": _DISPLAY_NAMES,
            "supported_locales": list(SUPPORTED_LOCALES),
            "capabilities": [
                "ai_order_parse",
                "line_order_ingest",
                "manual_review",
                "usage_status",
                "plan_catalog",
            ],
            "registration_endpoint": "/api/v1/module/orderai/registrations",
            "health_endpoint": "/api/v1/module/orderai/health",
            "event_types": list(event_types),
            "status": "available",
        }

    @staticmethod
    def build_event(
        *,
        event_type: str,
        company_id: int,
        idempotency_key: str,
        payload: dict[str, Any],
        signing_secret: str,
    ) -> dict[str, Any]:
        if not signing_secret:
            raise RuntimeError("MODULE_EVENT_SIGNING_SECRET not configured")
        event = {
            "event_id": str(uuid4()),
            "event_version": MODULE_VERSION,
            "event_type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "company_id": int(company_id),
            "idempotency_key": idempotency_key,
            "payload": payload,
        }
        canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        event["signature"] = hmac.new(
            signing_secret.encode("utf-8"), canonical.encode("utf-8"), sha256
        ).hexdigest()
        return event
