"""Team 5 衝刺證據工具；只用合成資料，不連線外部服務或正式資料庫。"""
from __future__ import annotations

import asyncio
import json

import httpx

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult, ILLMProvider, LLMProviderExecutionError
from app.providers.failover_llm import FailoverLLMProvider
from app.services import order_risk_service
from app.services.pii_redaction import redact_pii


class _NoSettingsDb:
    def get(self, *_args, **_kwargs):
        return None


class _FailureProvider(ILLMProvider):
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def extract_order(self, image_url=None, text=None, industry_type="ecom") -> ExtractionResult:
        raise self.error


def _decision(confidence: float) -> dict:
    extraction = ExtractionResult(
        items=[ExtractedItem(product_name="合成蘋果", quantity=2, evidence="合成蘋果 2 顆", confidence_score=confidence)],
        confidence_score=confidence,
    )
    decision = order_risk_service.evaluate_order_extraction(
        _NoSettingsDb(), extraction, [{"matched_product_id": 1}], default_threshold=0.85
    )
    return {"confidence": confidence, "status": decision.status, "reason_codes": decision.reasons}


async def _failure_reason(error: Exception) -> str:
    provider = FailoverLLMProvider(_FailureProvider(error), _FailureProvider(error))
    try:
        await provider.extract_order(text="合成訂單")
    except LLMProviderExecutionError as exc:
        return exc.reason_code
    raise RuntimeError("fail-closed evidence unavailable")


def main() -> None:
    original = "我是合成客戶，電話 0912-345-678，信箱 synthetic@example.com，合成蘋果 2 顆"
    output = {
        "threshold_084": _decision(0.84),
        "threshold_086": _decision(0.86),
        "llm_input_redacted": redact_pii(original),
        "audit_safe_fields": ["source_sha256", "reason_codes", "confidence_score", "item_count"],
        "provider_error_reason": asyncio.run(_failure_reason(RuntimeError("synthetic provider error"))),
        "provider_timeout_reason": asyncio.run(_failure_reason(httpx.TimeoutException("synthetic timeout"))),
        "module_lifecycle_events": [],
        "cross_module_company_id_type": "undetermined",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
