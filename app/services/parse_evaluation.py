"""訂單解析離線評測工具。

輸入為去識別化 JSONL 標註資料，每列包含 expected 與 actual 商品陣列；未連線任何模型或生產資料。
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ParseMetrics:
    samples: int
    expected_items: int
    actual_items: int
    matched_items: int
    item_precision: float
    item_recall: float
    item_f1: float
    exact_match_rate: float


def _normalize_name(value: object) -> str:
    return "".join(unicodedata.normalize("NFKC", str(value or "")).lower().split())


def _item_key(item: dict) -> tuple[str, int]:
    return _normalize_name(item.get("product_name")), int(item.get("quantity") or 0)


def evaluate_records(records: Iterable[dict]) -> ParseMetrics:
    sample_count = expected_count = actual_count = matched_count = exact_count = 0
    for record in records:
        expected = [_item_key(item) for item in (record.get("expected") or []) if isinstance(item, dict)]
        actual = [_item_key(item) for item in (record.get("actual") or []) if isinstance(item, dict)]
        remaining = list(expected)
        matched = 0
        for item in actual:
            if item in remaining:
                remaining.remove(item)
                matched += 1
        sample_count += 1
        expected_count += len(expected)
        actual_count += len(actual)
        matched_count += matched
        if sorted(expected) == sorted(actual):
            exact_count += 1

    precision = matched_count / actual_count if actual_count else 0.0
    recall = matched_count / expected_count if expected_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return ParseMetrics(
        samples=sample_count,
        expected_items=expected_count,
        actual_items=actual_count,
        matched_items=matched_count,
        item_precision=precision,
        item_recall=recall,
        item_f1=f1,
        exact_match_rate=exact_count / sample_count if sample_count else 0.0,
    )


def evaluate_jsonl(path: Path) -> ParseMetrics:
    with path.open("r", encoding="utf-8") as source:
        records = [json.loads(line) for line in source if line.strip()]
    return evaluate_records(records)


def metrics_as_dict(metrics: ParseMetrics) -> dict:
    return asdict(metrics)
