"""訂單解析風險守衛。

在建立訂單之前檢查信心、型錄命中、數量上限與原文佐證；拒絕時 fail-closed，並寫入去識別化稽核軌跡。
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.core.interfaces.llm_provider import ExtractionResult
from app.models import AuditLog
from app.services.settings_service import get_float_setting, get_int_setting


@dataclass(frozen=True)
class RiskDecision:
    status: str
    reasons: List[str]
    threshold: float


def evaluate_order_extraction(
    db: Session,
    extraction: ExtractionResult,
    priced_items: Iterable[dict],
    default_threshold: float,
) -> RiskDecision:
    """回傳 approve 或 needs_review；任一資料完整性檢查失敗即不允許自動建單。"""
    threshold = get_float_setting(db, "ai_confidence_threshold", default_threshold)
    threshold = min(1.0, max(0.0, threshold))
    max_items = get_int_setting(db, "ai_max_items_per_order", 30)
    max_qty = get_int_setting(db, "ai_max_quantity_per_item", 99)

    reasons: List[str] = []
    if extraction.confidence_score < threshold:
        reasons.append("confidence_below_threshold")
    if not extraction.items:
        reasons.append("no_items_extracted")
    if len(extraction.items) > max_items:
        reasons.append("item_count_exceeds_limit")

    priced = list(priced_items)
    if len(priced) != len(extraction.items):
        reasons.append("catalog_validation_incomplete")
    for index, item in enumerate(extraction.items):
        if not item.product_name:
            reasons.append("missing_product_name")
        if not item.evidence:
            reasons.append("missing_source_evidence")
        if item.quantity is None or not isinstance(item.quantity, int) or item.quantity < 1:
            reasons.append("invalid_quantity")
        elif item.quantity > max_qty:
            reasons.append("quantity_exceeds_limit")
        if item.confidence_score < threshold:
            reasons.append("item_confidence_below_threshold")
        if index >= len(priced) or priced[index].get("matched_product_id") is None:
            reasons.append("catalog_product_unmatched")

    unique_reasons = sorted(set(reasons))
    return RiskDecision(
        status="approved" if not unique_reasons else "needs_review",
        reasons=unique_reasons,
        threshold=threshold,
    )


def audit_ai_decision(
    db: Session,
    *,
    principal: dict,
    extraction: Optional[ExtractionResult],
    decision: RiskDecision,
    source_text: str,
) -> None:
    """僅記錄雜湊與控制資訊，不把 LINE 原文、電話或 API Key 寫進 audit_logs。"""
    db.add(
        AuditLog(
            user_id=principal.get("user_id"),
            store_id=principal.get("store_id"),
            action="ai.order.decision",
            resource_type="order",
            resource_id=None,
            new_value={
                "status": decision.status,
                "reason_codes": decision.reasons,
                "threshold": decision.threshold,
                "confidence_score": extraction.confidence_score if extraction else None,
                "provider": extraction.provider_name if extraction else None,
                "item_count": len(extraction.items) if extraction else 0,
                "source_sha256": sha256(source_text.encode("utf-8")).hexdigest(),
            },
        )
    )
    db.commit()
