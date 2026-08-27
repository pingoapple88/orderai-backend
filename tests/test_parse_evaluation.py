from pathlib import Path

import pytest

from app.services.parse_evaluation import evaluate_jsonl, evaluate_records


def test_exact_match_treats_fullwidth_and_spacing_as_same_product_name():
    metrics = evaluate_records([
        {
            "expected": [{"product_name": "高麗菜", "quantity": 2}],
            "actual": [{"product_name": "高　麗　菜", "quantity": 2}],
        }
    ])
    assert metrics.exact_match_rate == 1.0
    assert metrics.item_f1 == 1.0


def test_wrong_quantity_is_not_an_exact_or_item_match():
    metrics = evaluate_records([
        {
            "expected": [{"product_name": "蘋果", "quantity": 2}],
            "actual": [{"product_name": "蘋果", "quantity": 3}],
        }
    ])
    assert metrics.exact_match_rate == 0.0
    assert metrics.item_precision == 0.0
    assert metrics.item_recall == 0.0


def test_item_precision_and_recall_measure_extra_and_missing_items():
    metrics = evaluate_records([
        {
            "expected": [
                {"product_name": "蘋果", "quantity": 2},
                {"product_name": "香蕉", "quantity": 1},
            ],
            "actual": [
                {"product_name": "蘋果", "quantity": 2},
                {"product_name": "西瓜", "quantity": 1},
            ],
        }
    ])
    assert metrics.matched_items == 1
    assert metrics.item_precision == 0.5
    assert metrics.item_recall == 0.5
    assert metrics.exact_match_rate == 0.0


def test_malformed_actual_quantity_is_scored_as_unmatched_not_exception():
    metrics = evaluate_records([
        {
            "expected": [{"product_name": "蘋果", "quantity": 2}],
            "actual": [{"product_name": "蘋果", "quantity": "two"}],
        }
    ])
    assert metrics.exact_match_rate == 0.0
    assert metrics.matched_items == 0


def test_jsonl_reports_line_number_for_malformed_input(tmp_path: Path):
    path = tmp_path / "broken.jsonl"
    path.write_text('{"expected": []}\nnot-json\n', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_jsonl_line:2"):
        evaluate_jsonl(path)
