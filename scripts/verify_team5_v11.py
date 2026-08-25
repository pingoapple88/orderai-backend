"""Team 5 v1.1 驗收證據工具；只用合成資料，不連線外部服務或正式資料庫。"""
from __future__ import annotations

import asyncio
import hmac
import json
from hashlib import sha256

import httpx

from app.adapters.merchcore_module import OrderAIMerchCoreAdapter
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
        items=[
            ExtractedItem(
                product_name="合成蘋果",
                quantity=2,
                evidence="合成蘋果 2 顆",
                confidence_score=confidence,
            )
        ],
        confidence_score=confidence,
    )
    decision = order_risk_service.evaluate_order_extraction(
        _NoSettingsDb(),
        extraction,
        [{"matched_product_id": 1}],
        default_threshold=0.85,
    )
    return {"confidence": confidence, "status": decision.status, "reason_codes": decision.reasons}


async def _failure_reason(error: Exception) -> str:
    provider = FailoverLLMProvider(_FailureProvider(error), _FailureProvider(error))
    try:
        await provider.extract_order(text="合成訂單")
    except LLMProviderExecutionError as exc:
        return exc.reason_code
    raise RuntimeError("fail-closed evidence unavailable")


def _event_evidence() -> dict:
    secret = "synthetic-signing-secret"
    event = OrderAIMerchCoreAdapter.build_event(
        event_type="contract.module.registration",
        company_id=101,
        idempotency_key="synthetic-idempotency-key",
        payload={"module_key": "orderai", "store_key": "ord_synthetic", "status": "pending_activation"},
        signing_secret=secret,
    )
    unsigned = {key: value for key, value in event.items() if key != "signature"}
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "event": event,
        "signature_valid": hmac.compare_digest(
            event["signature"],
            hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), sha256).hexdigest(),
        ),
    }


def main() -> None:
    original = "我是合成客戶，電話 0912-345-678，信箱 synthetic@example.com，合成蘋果 2 顆"
    output = {
        "threshold_084": _decision(0.84),
        "threshold_086": _decision(0.86),
        "llm_input_redacted": redact_pii(original),
        "audit_safe_fields": ["source_sha256", "reason_codes", "confidence_score", "item_count"],
        "provider_error_reason": asyncio.run(_failure_reason(RuntimeError("synthetic provider error"))),
        "provider_timeout_reason": asyncio.run(_failure_reason(httpx.TimeoutException("synthetic timeout"))),
        "event_evidence": _event_evidence(),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
