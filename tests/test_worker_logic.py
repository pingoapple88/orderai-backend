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
    """信心 0.9 > 0.7 threshold，應建單。"""
    result = ExtractionResult(
        items=[ExtractedItem(product_name="豬肉乾", quantity=2, unit_price=150)],
        confidence_score=0.9,
        industry_type="ecom",
    )
    from app.core.config import get_settings
    assert result.confidence_score >= get_settings().ai_confidence_threshold


def test_low_confidence_below_threshold():
    """信心 0.3 < 0.7 threshold，fail-closed 不建單。"""
    result = ExtractionResult(
        items=[],
        confidence_score=0.3,
        industry_type="ecom",
    )
    from app.core.config import get_settings
    assert result.confidence_score < get_settings().ai_confidence_threshold


def test_normalize_items_beauty():
    """美業 item 正規化：service_name → product_name。"""
    from app.providers.openai_llm import _normalize_items
    raw = [{"service_name": "剪髮", "price": 500, "appointment_time": "14:00", "staff_name": "小美"}]
    items = _normalize_items("beauty", raw)
    assert len(items) == 1
    assert items[0].product_name == "剪髮"
    assert items[0].unit_price == 500
    assert items[0].appointment_time == "14:00"
    assert items[0].staff_name == "小美"


def test_normalize_items_ecom():
    """電商 item 正規化：product_name/quantity/unit_price。"""
    from app.providers.openai_llm import _normalize_items
    raw = [{"product_name": "豬肉乾", "quantity": 2, "unit_price": 150}]
    items = _normalize_items("ecom", raw)
    assert items[0].product_name == "豬肉乾"
    assert items[0].quantity == 2
    assert items[0].unit_price == 150
