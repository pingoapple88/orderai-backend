"""青泉谷 P1 OrderAI 隔離 UAT 合成基準的手動 CLI。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.core.database import SessionLocal
from app.p1_uat_seed import P1UatSeedBlocked, clear_p1_uat, seed_p1_uat, verify_p1_uat_baseline


def main() -> int:
    parser = argparse.ArgumentParser(description="只限隔離青泉谷 P1 UAT 的手動合成種子／驗證／清理")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", action="store_true", help="建立或取得可重跑的合成基準")
    group.add_argument("--verify", action="store_true", help="唯讀驗證零正式副作用")
    group.add_argument("--clear", action="store_true", help="清除精準合成資料；偵測正式副作用即停止")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.seed:
            print(json.dumps({"action": "seed", **seed_p1_uat(db).safe_summary()}, ensure_ascii=False, sort_keys=True))
        elif args.verify:
            print(json.dumps({"action": "verify", **verify_p1_uat_baseline(db)}, ensure_ascii=False, sort_keys=True))
        else:
            clear_p1_uat(db)
            print(json.dumps({"action": "clear", "cleared": True, "synthetic_only": True}, ensure_ascii=False))
    except P1UatSeedBlocked as exc:
        db.rollback()
        print(json.dumps({"blocked": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
