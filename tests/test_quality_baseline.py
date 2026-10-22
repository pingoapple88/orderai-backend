"""Focused tests for the repository quality baseline comparator."""
from __future__ import annotations

from pathlib import Path

from scripts.capture_quality_baseline import (
    QualitySnapshot,
    compare_snapshots,
    parse_mypy_output,
    parse_ruff_output,
    pytest_summary,
)

REPOSITORY = Path("/tmp/orderai-quality-repository")


def test_parse_ruff_output_returns_rule_counts_and_stable_signatures() -> None:
    raw = (
        '[{"filename": "/tmp/orderai-quality-repository/app/a.py", '
        '"code": "I001", "message": "Import block is unsorted"}, '
        '{"filename": "/tmp/orderai-quality-repository/app/a.py", '
        '"code": "F401", "message": "Unused import"}]'
    )

    signatures, rule_counts = parse_ruff_output(raw, REPOSITORY)

    assert signatures == [
        "app/a.py|F401|Unused import",
        "app/a.py|I001|Import block is unsorted",
    ]
    assert rule_counts == {"F401": 1, "I001": 1}


def test_parse_mypy_output_ignores_summary_and_normalizes_paths() -> None:
    raw = "\n".join(
        [
            "app/a.py:10: error: Bad value  [arg-type]",
            "Found 1 error in 1 file (checked 2 source files)",
        ]
    )

    signatures = parse_mypy_output(raw, REPOSITORY)

    assert signatures == ["app/a.py|arg-type|Bad value"]


def test_compare_snapshots_classifies_new_and_fixed_diagnostics() -> None:
    base = QualitySnapshot(
        label="base",
        repository="/tmp/base",
        revision="base-sha",
        python_version="3.12.1",
        pytest_exit=0,
        pytest_summary="1 passed",
        ruff_exit=1,
        ruff_diagnostics=2,
        ruff_rule_counts={"F401": 1, "I001": 1},
        mypy_exit=1,
        mypy_errors=1,
        compileall_exit=0,
        diff_check_exit=0,
        ruff_signatures=["app/a.py|F401|Unused", "app/b.py|I001|Sort"],
        mypy_signatures=["app/a.py|arg-type|Bad"],
    )
    current = QualitySnapshot(
        label="current",
        repository="/tmp/current",
        revision="current-sha",
        python_version="3.12.1",
        pytest_exit=0,
        pytest_summary="1 passed",
        ruff_exit=1,
        ruff_diagnostics=2,
        ruff_rule_counts={"F401": 1, "BLE001": 1},
        mypy_exit=1,
        mypy_errors=1,
        compileall_exit=0,
        diff_check_exit=0,
        ruff_signatures=["app/a.py|F401|Unused", "app/c.py|BLE001|Catch"],
        mypy_signatures=["app/a.py|arg-type|Bad"],
    )

    comparison = compare_snapshots(base, current)

    assert comparison["ruff"] == {
        "base": 2,
        "current": 2,
        "existing": 1,
        "new": ["app/c.py|BLE001|Catch"],
        "fixed": ["app/b.py|I001|Sort"],
    }
    assert comparison["mypy"]["new"] == []
    assert comparison["mypy"]["fixed"] == []


def test_pytest_summary_uses_last_result_line() -> None:
    assert pytest_summary("...\n2 passed, 1 skipped in 0.10s\n") == "2 passed, 1 skipped in 0.10s"
