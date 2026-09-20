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

        match = re.search(
            r"(?P<product>青泉谷蛋)\s*(?P<quantity>[1-9][0-9]?)\s*(?P<unit>盒|箱).*(?:明天|明日)\s*(?P<period>上午|下午)?\s*(?P<hour>[0-9]{1,2})\s*(?::(?P<minute>[0-5][0-9]))?\s*(?:取貨|自取)",
            text,
        )
        if match is None:
            return self._empty_result()

        quantity = int(match.group("quantity"))
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or "0")
        if match.group("period") == "下午" and hour < 12:
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
                    product_name=match.group("product"),
                    quantity=quantity,
                    unit=match.group("unit"),
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
    def _empty_result() -> ExtractionResult:
        return ExtractionResult(
            confidence_score=0.0,
            industry_type="ecom",
            provider_name="synthetic_staging_rule_based",
            raw={"special_request": "", "synthetic_staging": True},
        )
