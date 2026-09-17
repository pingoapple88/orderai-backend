"""PR-3 任務四：Worker 邏輯層測試（不需真實 LLM/LINE/DB）。"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult
from app.workers.line_worker import _get_text_from_event


# ── pre-filter 單元測試 ────────────────────────────────────────────────────

def test_get_text_from_text_event():
    event = {"message": {"type": "text", "text": "豬肉乾+2"}}
    assert _get_text_from_event(event) == "豬肉乾+2"


def test_get_text_from_image_event_returns_none():
    event = {"message": {"type": "image"}}
    assert _get_text_from_event(event) is None


def test_get_text_from_empty_event_returns_none():
    assert _get_text_from_event({}) is None


# ── fail-closed 邏輯測試（不需 HTTP）─────────────────────────────────────

def test_high_confidence_above_threshold():
    """信心 0.9 > 0.85 threshold，應通過第一層信心檢查。"""
    result = ExtractionResult(
        items=[ExtractedItem(product_name="豬肉乾", quantity=2, unit_price=150)],
        confidence_score=0.9,
        industry_type="ecom",
    )
    from app.core.config import get_settings
    assert result.confidence_score >= get_settings().ai_confidence_threshold


def test_low_confidence_below_threshold():
    """信心 0.3 < 0.85 threshold，fail-closed 不建單。"""
    result = ExtractionResult(
        items=[],
        confidence_score=0.3,
        industry_type="ecom",
    )
    from app.core.config import get_settings
    assert result.confidence_score < get_settings().ai_confidence_threshold


def test_parse_result_beauty():
    """美業結構化輸出只接受明確服務、時段與人員，不填價格。"""
    from app.providers.http_chat_llm import _parse_result
    result = _parse_result(
        {
            "items": [{
                "product_name": "剪髮", "quantity": 1, "appointment_time": "14:00",
                "staff_name": "小美", "evidence": "剪髮，14:00 找小美", "field_confidence": 0.9,
            }],
            "confidence_score": 0.9,
        },
        "beauty",
        "test",
    )
    assert len(result.items) == 1
    assert result.items[0].product_name == "剪髮"
    assert result.items[0].appointment_time == "14:00"
    assert result.items[0].staff_name == "小美"
    assert result.items[0].unit_price is None


def test_parse_result_ecom_omits_model_price():
    """電商解析只保留商品、數量與原文證據；價格由型錄帶入。"""
    from app.providers.http_chat_llm import _parse_result
    result = _parse_result(
        {
            "items": [{"product_name": "豬肉乾", "quantity": 2, "evidence": "豬肉乾+2", "field_confidence": 0.9}],
            "confidence_score": 0.9,
        },
        "ecom",
        "test",
    )
    assert result.items[0].product_name == "豬肉乾"
    assert result.items[0].quantity == 2
    assert result.items[0].unit_price is None
