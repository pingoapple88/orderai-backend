"""青泉谷 P1 隔離 UAT 真實 HMAC 驗收的手動 CLI。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.core.database import SessionLocal
from app.p1_uat_acceptance import (
    P1UatAcceptanceBlocked,
    resume_p1_uat_queued_no_attempt,
    run_p1_uat_acceptance,
    status_p1_uat_acceptance,
    verify_p1_uat_acceptance,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="只限隔離青泉谷 P1 UAT 的單次 OrderAI→ERP 真實 HMAC 驗收")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true", help="執行一次合成案例、人工覆核與真實 HMAC 交付")
    group.add_argument("--status", action="store_true", help="唯讀顯示固定合成案例與零副作用狀態；不建立資料、不送件")
    group.add_argument("--resume-queued-no-attempt", action="store_true", help="僅恢復固定 queued、零嘗試的中斷合成案例一次")
    group.add_argument("--verify", action="store_true", help="唯讀驗證既有交付及零正式交易副作用")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.run:
            summary = run_p1_uat_acceptance(db).safe_summary()
            action = "run"
        elif args.status:
            summary = status_p1_uat_acceptance(db)
            action = "status"
        elif args.resume_queued_no_attempt:
            summary = resume_p1_uat_queued_no_attempt(db).safe_summary()
            action = "resume_queued_no_attempt"
        else:
            summary = verify_p1_uat_acceptance(db)
            action = "verify"
        print(json.dumps({"action": action, **summary}, ensure_ascii=False, sort_keys=True))
    except P1UatAcceptanceBlocked as exc:
        db.rollback()
        print(json.dumps({"blocked": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
