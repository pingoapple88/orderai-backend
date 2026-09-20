"""Tests for the isolated synthetic staging ILLMProvider adapter."""
from __future__ import annotations

import asyncio

import pytest

from app import providers
from app.core.interfaces.llm_provider import LLMProviderExecutionError
from app.providers.synthetic_staging_llm import SyntheticStagingLLMProvider


def _allowed_provider() -> SyntheticStagingLLMProvider:
    return SyntheticStagingLLMProvider(
        enabled=True,
        environment="uat",
        railway_environment_name="staging",
        uat_marker="qingquan-p1-uat",
    )


def test_synthetic_staging_provider_parses_only_the_documented_synthetic_text_shape():
    result = asyncio.run(
        _allowed_provider().extract_order(text="【最終驗收】青泉谷蛋 2 盒，明天下午 3:00 取貨。")
    )

    assert result.provider_name == "synthetic_staging_rule_based"
    assert [(item.product_name, item.quantity, item.unit) for item in result.items] == [
        ("青泉谷 P1 UAT 合成商品", 2, "盒")
    ]
    assert result.raw["synthetic_staging"] is True
    assert result.raw["requested_for"].endswith("+08:00")


def test_synthetic_staging_provider_maps_chicken_egg_alias_to_synthetic_catalog():
    result = asyncio.run(
        _allowed_provider().extract_order(text="青泉谷雞蛋 2 盒，明天下午 3:00 取貨。")
    )

    assert [(item.product_name, item.quantity, item.unit) for item in result.items] == [
        ("青泉谷 P1 UAT 合成商品", 2, "盒")
    ]


def test_synthetic_staging_provider_accepts_chinese_pickup_hour():
    result = asyncio.run(
        _allowed_provider().extract_order(text="青泉谷雞蛋 2 盒，明天下午三點取貨。")
    )

    assert len(result.items) == 1
    assert result.raw["requested_for"].endswith("+08:00")


def test_synthetic_staging_provider_accepts_line_style_newlines_between_item_and_pickup_time():
    result = asyncio.run(
        _allowed_provider().extract_order(text="青泉谷雞蛋\n2盒\n明天下午三點\n取貨")
    )

    assert [(item.product_name, item.quantity, item.unit) for item in result.items] == [
        ("青泉谷 P1 UAT 合成商品", 2, "盒")
    ]
    assert result.raw["requested_for"].endswith("+08:00")


def test_synthetic_staging_provider_returns_empty_draft_for_unrecognised_text():
    result = asyncio.run(_allowed_provider().extract_order(text="這不是合成 UAT 格式"))

    assert result.items == []
    assert result.provider_name == "synthetic_staging_rule_based"
    assert result.raw["synthetic_staging"] is True


def test_synthetic_staging_provider_is_fail_closed_outside_exact_environment():
    blocked = SyntheticStagingLLMProvider(
        enabled=True,
        environment="production",
        railway_environment_name="staging",
        uat_marker="qingquan-p1-uat",
    )

    with pytest.raises(LLMProviderExecutionError, match="Synthetic staging provider") as error:
        asyncio.run(blocked.extract_order(text="青泉谷蛋 2 盒，明天下午 3:00 取貨"))
    assert error.value.reason_code == "synthetic_provider_not_allowed"


def test_provider_factory_keeps_synthetic_adapter_behind_externalised_guard(monkeypatch):
    monkeypatch.setattr(providers.settings, "p1_uat_synthetic_llm_enabled", True)
    monkeypatch.setattr(providers.settings, "environment", "uat")
    monkeypatch.setattr(providers.settings, "railway_environment_name", "staging")
    monkeypatch.setattr(providers.settings, "p1_uat_environment_marker", "qingquan-p1-uat")

    adapter = providers._build_llm_provider("synthetic_staging")

    assert isinstance(adapter, SyntheticStagingLLMProvider)
