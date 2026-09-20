"""Deterministic, non-network provider for isolated Qingquan P1 staging UAT.

This adapter is deliberately *not* an LLM. It exists only to exercise the same
ILLMProvider contract when production LLM credentials are not present. It may
never activate outside the exact synthetic staging guard and never approves or
forwards an order.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult, ILLMProvider, LLMProviderExecutionError

_TAIPEI = ZoneInfo("Asia/Taipei")
_UAT_MARKER = "qingquan-p1-uat"
_SYNTHETIC_CATALOG_PRODUCT = "青泉谷 P1 UAT 合成商品"
_CHINESE_HOURS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}


class SyntheticStagingLLMProvider(ILLMProvider):
    """Constrained text parser for the documented Qingquan synthetic UAT sentence."""

    def __init__(
        self,
        *,
        enabled: bool,
        environment: str,
        railway_environment_name: str,
        uat_marker: str,
    ) -> None:
        self._allowed = (
            enabled
            and environment.strip().lower() == "uat"
            and railway_environment_name.strip().lower() == "staging"
            and uat_marker == _UAT_MARKER
        )

    async def extract_order(
        self,
        image_url: str | None = None,
        text: str | None = None,
        industry_type: str = "ecom",
    ) -> ExtractionResult:
        if not self._allowed:
            raise LLMProviderExecutionError(
                "synthetic_provider_not_allowed",
                "Synthetic staging provider is disabled outside isolated UAT.",
            )
        if image_url is not None or industry_type != "ecom" or not text:
            return self._empty_result()

        item_match = re.search(
            r"(?P<product>青泉谷\s*(?:雞\s*)?蛋)\s*(?P<quantity>[1-9][0-9]?)\s*(?P<unit>盒|箱)",
            text,
            flags=re.DOTALL,
        )
        pickup_match = re.search(
            r"(?:明天|明日).*?(?P<period>上午|下午)?\s*(?P<hour>[0-9]{1,2}|[一二三四五六七八九十]{1,2})(?::(?P<minute>[0-5][0-9]))?(?:點|时)?\s*(?:取貨|自取)",
            text,
            flags=re.DOTALL,
        )
        if item_match is None or pickup_match is None:
            return self._empty_result()

        quantity = int(item_match.group("quantity"))
        hour = self._parse_hour(pickup_match.group("hour"))
        if hour is None:
            return self._empty_result()
        minute = int(pickup_match.group("minute") or "0")
        if pickup_match.group("period") == "下午" and hour < 12:
            hour += 12
        if not 0 <= hour <= 23:
            return self._empty_result()

        local_now = datetime.now(_TAIPEI)
        requested_for = (local_now + timedelta(days=1)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        return ExtractionResult(
            items=[
                ExtractedItem(
                    # Synthetic alias mapping is explicit: this adapter never maps
                    # to a production catalog or an unscoped product identity.
                    product_name=_SYNTHETIC_CATALOG_PRODUCT,
                    quantity=quantity,
                    unit=item_match.group("unit"),
                    evidence="synthetic_staging_rule_match",
                    confidence_score=0.70,
                )
            ],
            confidence_score=0.70,
            field_confidence={"product_name": 0.70, "quantity": 0.70, "requested_for": 0.70},
            industry_type="ecom",
            provider_name="synthetic_staging_rule_based",
            raw={
                "requested_for": requested_for.isoformat(),
                "special_request": "",
                "synthetic_staging": True,
            },
        )

    @staticmethod
    def _parse_hour(value: str) -> int | None:
        if value.isdigit():
            return int(value)
        return _CHINESE_HOURS.get(value)

    @staticmethod
    def _empty_result() -> ExtractionResult:
        return ExtractionResult(
            confidence_score=0.0,
            industry_type="ecom",
            provider_name="synthetic_staging_rule_based",
            raw={"special_request": "", "synthetic_staging": True},
        )
