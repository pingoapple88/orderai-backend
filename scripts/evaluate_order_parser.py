"""以去識別化標註資料集評測訂單解析結果。

JSONL 每列：{"expected": [{"product_name": "蘋果", "quantity": 2}],
            "actual": [{"product_name": "蘋果", "quantity": 2}]}
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.parse_evaluation import evaluate_jsonl, metrics_as_dict


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--minimum-exact-match", type=float, default=0.95)
    args = parser.parse_args()
    metrics = evaluate_jsonl(args.dataset)
    print(json.dumps(metrics_as_dict(metrics), ensure_ascii=False, indent=2))
    return 0 if metrics.exact_match_rate >= args.minimum_exact_match else 2


if __name__ == "__main__":
    raise SystemExit(main())
