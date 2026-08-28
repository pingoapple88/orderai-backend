"""Run T5's local, synthetic CI checks and emit redacted evidence metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "evidence" / "t5_cicd_entrypoint_manifest.json"
FOCUSED_TESTS = [
    "tests/test_parse_normalizer.py",
    "tests/test_parse_evaluation.py",
    "tests/test_i18n_contract.py",
    "tests/ui/orderai/test_orderai_ui_harness.py",
    "tests/ui/orderai/test_orderai_screen_renderer.py",
    "tests/test_demo_orderai_contract.py",
]
FORBIDDEN_PATHS = re.compile(r"^(app/api/v1/auth\.py|tests/test_auth_callback\.py|alembic/|migrations/|Dockerfile|docker-compose|\.env)")
FORBIDDEN_RUNTIME = re.compile(r"https?://|www\.|requests\.|httpx\.|urllib|fetch\(|webhook|redis://|postgresql://|mysql://|api[_-]?key|secret|password|token|analytics|telemetry|beacon|cdn", re.IGNORECASE)
FORBIDDEN_EXPOSURE = re.compile(r"company_id|companyId|store_key|storeId|reply_token|replyToken|[\w.+-]+@[\w.-]+|\b\d{8,}\b", re.IGNORECASE)


def _run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "command": " ".join(command),
        "expected_exit_code": 0,
        "actual_exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _scan_assets() -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    targets = [ROOT / "src" / "ui", ROOT / "src" / "adapters" / "orderai_adapter.py"]
    for target in targets:
        paths = target.rglob("*") if target.is_dir() else [target]
        for path in paths:
            if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            text = path.read_text(encoding="utf-8")
            for expression, category in ((FORBIDDEN_RUNTIME, "runtime"), (FORBIDDEN_EXPOSURE, "exposure")):
                match = expression.search(text)
                if match:
                    findings.append({"path": str(path.relative_to(ROOT)), "category": category, "line": str(text[: match.start()].count("\n") + 1)})
    return {
        "command": "python3 ci/t5_orderai_ui_checks.py --output evidence/t5_cicd_entrypoint_manifest.json",
        "expected_exit_code": 0,
        "actual_exit_code": 0 if not findings else 1,
        "findings": findings,
    }


def _required_paths() -> list[str]:
    return [
        "src/ui/fixtures/orderai/orderai_screen_scenarios.json",
        "src/ui/contracts/orderai/orderai.parse_result.json",
        "src/ui/contracts/orderai/orderai.risk_review.json",
        "src/ui/contracts/orderai/orderai.queue.json",
        "src/ui/screens/orderai/renderer.py",
        "src/ui/screens/orderai/orderai_screens.css",
        "src/ui/screens/orderai/orderai_screen_interactions.js",
        "tests/ui/orderai/test_orderai_ui_harness.py",
        "tests/ui/orderai/test_orderai_screen_renderer.py",
    ]


def _evidence_path(output_path: Path) -> str:
    try:
        return str(output_path.relative_to(ROOT))
    except ValueError:
        return str(output_path)


def run_checks(output_path: Path) -> dict[str, Any]:
    branch = _git("branch", "--show-current")
    if branch == "main":
        raise RuntimeError("HARD_GATE: T5 CI entrypoint refuses main branch execution")
    for relative_path in _required_paths():
        if not (ROOT / relative_path).is_file():
            raise RuntimeError(f"BLOCKED_BY_MISSING_EVIDENCE: {relative_path}")

    test_check = _run([sys.executable, "-m", "pytest", "-q", *FOCUSED_TESTS])
    compile_check = _run([sys.executable, "-m", "compileall", "-q", "src", "tests/ui/orderai"])
    diff_check = _run(["git", "diff", "--check"])
    scan_check = _scan_assets()
    checks = {
        "test": test_check,
        "compile": compile_check,
        "diff_check": diff_check,
        "scan": scan_check,
    }
    failures = [name for name, result in checks.items() if result["actual_exit_code"] != result["expected_exit_code"]]
    manifest = {
        "schema_version": "T5-CICD-EVIDENCE-01",
        "run_id": f"t5-{_git('rev-parse', '--short', 'HEAD')}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "team": "T5",
        "repository": "pingoapple88/orderai-backend",
        "branch": branch,
        "head_40_chars": _git("rev-parse", "HEAD"),
        "parent_40_chars": _git("rev-parse", "HEAD^"),
        "triggered_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "workflow_version": "T5-CICD-EVIDENCE-01",
        "test_command": test_check["command"],
        "compile_command": compile_check["command"],
        "diff_check_command": diff_check["command"],
        "scan_command": scan_check["command"],
        "fixture_path": "src/ui/fixtures/orderai/orderai_screen_scenarios.json",
        "screen_contract_version": "ORDERAI-UI-W2-01",
        "harness_path": "tests/ui/orderai/test_orderai_ui_harness.py; tests/ui/orderai/test_orderai_screen_renderer.py",
        "required_env_names_only": [],
        "expected_exit_code": {name: result["expected_exit_code"] for name, result in checks.items()},
        "actual_exit_code": {name: result["actual_exit_code"] for name, result in checks.items()},
        "evidence_paths": [_evidence_path(output_path), "evidence/t5_cicd_entrypoint_run.log"],
        "rollback_reference": _git("rev-parse", "HEAD^"),
        "open_todos": [
            "[TODO: 待人工確認] 獨立 OAuth PR #22 尚未合併至 main；完整 pytest 的既有 Auth state-cookie failure 不可夾帶至 T5。",
            "[TODO: 待 Auth baseline 解鎖] 完整 pytest 依現有 tests/conftest 的 Alembic／可丟棄 DB 前置與獨立 OAuth baseline 處理；本 CI entrypoint 僅執行不需資料庫的 synthetic focused suite。",
            "[TODO: 待 T1 接入] T1 需以 pinned manifest 掛載三個 OrderAI local screen assets，並提供瀏覽器證據。",
        ],
        "cross_team_requests": ["XREQ-0002: T5→T1 local renderer、CSS、interaction 與 fixture 接入。"],
        "checks": checks,
        "blocking_level": "READY_FOR_R1" if not failures else "RETURN_FOR_FIX",
        "redaction_status": "SYNTHETIC_ONLY",
        "external_connection_status": "MATCH=NO" if not scan_check["findings"] else "MATCH=YES",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Run T5 local synthetic CI checks.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    output_path = arguments.output if arguments.output.is_absolute() else ROOT / arguments.output
    manifest = run_checks(output_path)
    print(json.dumps({"run_id": manifest["run_id"], "blocking_level": manifest["blocking_level"], "actual_exit_code": manifest["actual_exit_code"]}, ensure_ascii=False))
    return 0 if manifest["blocking_level"] == "READY_FOR_R1" else 1


if __name__ == "__main__":
    os.environ.pop("DATABASE_URL", None)
    raise SystemExit(main())
