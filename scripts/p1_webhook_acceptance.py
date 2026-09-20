"""CLI for the fail-closed Qingquangu P1 synthetic signed-LINE-webhook acceptance."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.p1_webhook_acceptance import P1WebhookAcceptanceBlocked, run_p1_webhook_acceptance


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只限明確 allowlist 的 localhost 或隔離 UAT：簽章合成 LINE webhook 人工覆核驗收"
    )
    parser.add_argument("--run", action="store_true", help="送出一筆合成 webhook 與同一筆 replay，輸出去識別化 JSON 證據")
    parser.add_argument("--timeout-seconds", type=float, default=15.0, help="等待既有 worker 寫入 needs_human_review 的上限（1–120 秒）")
    args = parser.parse_args()
    if not args.run:
        parser.error("必須明確指定 --run；工具不提供預設寫入行為")
    try:
        summary = run_p1_webhook_acceptance(timeout_seconds=args.timeout_seconds)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    except P1WebhookAcceptanceBlocked as exc:
        # Error codes identify only the guard failure; never echo host, URL,
        # raw request, database URL, signing secret, or event identifiers.
        print(json.dumps({"blocked": str(exc), "passed": False}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
