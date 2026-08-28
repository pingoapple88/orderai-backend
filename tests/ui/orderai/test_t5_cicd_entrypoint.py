"""Contract tests for T5's repository-local, synthetic CI entrypoint."""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENTRYPOINT = ROOT / "ci" / "t5_orderai_ui_checks.py"


def test_t5_cicd_entrypoint_emits_complete_redacted_manifest(tmp_path: Path):
    output = tmp_path / "t5_cicd_evidence.json"
    completed = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads(output.read_text(encoding="utf-8"))
    required_fields = {
        "team", "repository", "branch", "head_40_chars", "parent_40_chars", "test_command",
        "compile_command", "diff_check_command", "scan_command", "fixture_path", "screen_contract_version",
        "harness_path", "required_env_names_only", "expected_exit_code", "actual_exit_code", "evidence_paths",
        "rollback_reference", "open_todos", "cross_team_requests", "checks", "blocking_level",
    }
    assert required_fields <= set(manifest)
    assert manifest["team"] == "T5"
    assert manifest["branch"].startswith("feat/") and manifest["branch"] != "main"
    assert len(manifest["head_40_chars"]) == 40 and len(manifest["parent_40_chars"]) == 40
    assert manifest["screen_contract_version"] == "ORDERAI-UI-W2-01"
    assert manifest["required_env_names_only"] == []
    assert manifest["actual_exit_code"] == {"test": 0, "compile": 0, "diff_check": 0, "scan": 0}
    assert manifest["blocking_level"] == "READY_FOR_R1"
    assert "DATABASE_URL" not in output.read_text(encoding="utf-8")


def test_t5_cicd_entrypoint_is_local_only_and_calls_existing_harnesses():
    source = ENTRYPOINT.read_text(encoding="utf-8")

    assert "tests/ui/orderai/test_orderai_ui_harness.py" in source
    assert "tests/ui/orderai/test_orderai_screen_renderer.py" in source
    assert "tests/test_demo_orderai_contract.py" in source
    assert "tests/test_parse_normalizer.py" in source
    assert "tests/test_parse_evaluation.py" in source
    assert "tests/test_i18n_contract.py" in source
    assert "tests/ui/orderai/test_t5_cicd_entrypoint.py" not in source
    assert "subprocess.run" in source
    assert "requests." not in source and "httpx." not in source
    assert "DATABASE_URL" not in source or "os.environ.pop(\"DATABASE_URL\"" in source
