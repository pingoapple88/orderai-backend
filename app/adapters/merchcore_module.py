"""OrderAI 模組描述 Adapter；本輪不宣告或產生任何模組生命週期事件。"""
from __future__ import annotations

from typing import Any


SUPPORTED_LOCALES = ("zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID")
MODULE_KEY = "orderai"
MODULE_VERSION = "1.8"

_DISPLAY_NAMES = {
    "zh-Hant-TW": "OrderAI 訂單解析服務",
    "en-US": "OrderAI Order Parsing Service",
    "th-TH": "บริการวิเคราะห์คำสั่งซื้อ OrderAI",
    "ja-JP": "OrderAI 注文解析サービス",
    "id-ID": "Layanan Analisis Pesanan OrderAI",
}


def normalize_locale(locale: str | None) -> str:
    return locale if locale in SUPPORTED_LOCALES else "zh-Hant-TW"


class OrderAIMerchCoreAdapter:
    """只提供模組描述；不連線或耦合其他模組資料庫，也不產生生命週期事件。"""

    @staticmethod
    def module_manifest() -> dict[str, Any]:
        return {
            "moduleKey": MODULE_KEY,
            "moduleVersion": MODULE_VERSION,
            "displayName": _DISPLAY_NAMES,
            "supportedLocales": list(SUPPORTED_LOCALES),
            "capabilities": [
                "ai_order_parse",
                "line_order_ingest",
                "manual_review",
                "usage_status",
                "plan_catalog",
            ],
            "registrationEndpoint": "/api/v1/module/orderai/registrations",
            "healthEndpoint": "/api/v1/module/orderai/health",
            "status": "available",
        }
