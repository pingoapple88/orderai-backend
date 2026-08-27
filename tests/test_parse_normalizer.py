import pytest

from app.providers.http_chat_llm import _parse_result
from app.services.parse_normalizer import clean_product_name, normalize_product_key, normalize_quantity


@pytest.mark.parametrize(
    ("raw", "expected", "reason"),
    [
        ("２", 2, None),
        (2, 2, None),
        (0, None, "quantity_not_positive"),
        (-1, None, "quantity_not_positive"),
        (True, None, "quantity_not_integer"),
        (1.0, None, "quantity_float_not_allowed"),
        ("1.5", None, "quantity_not_integer"),
        ("", None, "quantity_not_integer"),
        (None, None, "quantity_missing"),
    ],
)
def test_normalize_quantity_is_strict_and_classified(raw, expected, reason):
    result = normalize_quantity(raw, max_quantity=99)
    assert result.value == expected
    assert result.reason_code == reason


def test_normalize_quantity_enforces_supplied_limit():
    result = normalize_quantity("100", max_quantity=99)
    assert result.value is None
    assert result.reason_code == "quantity_exceeds_limit"


def test_product_name_key_is_unicode_case_and_whitespace_stable():
    assert clean_product_name("  Ａｐｐｌｅ　 ") == "Apple"
    assert normalize_product_key("  Ａｐｐｌｅ　 ") == "apple"
    assert normalize_product_key("高　麗　菜") == normalize_product_key("高麗菜")


def test_provider_ignores_unknown_and_price_fields_and_marks_invalid_quantity():
    result = _parse_result(
        {
            "items": [
                {
                    "product_name": "  Ａｐｐｌｅ ",
                    "quantity": 1.0,
                    "unit_price": 12.5,
                    "evidence": "Ａｐｐｌｅ 1",
                    "field_confidence": 0.9,
                    "injected": "ignored",
                }
            ],
            "confidence_score": "NaN",
            "unknown_top_level": "ignored",
        },
        "ecom",
        "fake",
    )
    assert result.items[0].product_name == "Apple"
    assert result.items[0].quantity is None
    assert result.items[0].unit_price is None
    assert result.confidence_score == 0.0
    assert result.raw == {"item_count": 1}


@pytest.mark.parametrize("payload", [None, {"items": "not-a-list"}, {"items": 3, "field_confidence": []}])
def test_provider_malformed_payload_becomes_empty_low_confidence_result(payload):
    result = _parse_result(payload, "ecom", "fake")
    assert result.items == []
    assert result.confidence_score == 0.0
    assert result.field_confidence == {}
    assert result.raw == {"item_count": 0}
