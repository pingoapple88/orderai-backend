#!/usr/bin/env python3
"""Capture and compare the repository quality baseline without hiding failures."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MYPY_ERROR_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+): error: (?P<message>.*?)(?:  \[(?P<code>[^]]+)\])?$"
)
PYTHON_VERSION_RE = re.compile(r"Python (?P<version>\d+\.\d+\.\d+)")


@dataclass(frozen=True)
class CommandResult:
    name: str
    command: list[str]
    exit_code: int
    stdout_file: str
    stderr_file: str


@dataclass(frozen=True)
class QualitySnapshot:
    label: str
    repository: str
    revision: str
    python_version: str
    pytest_exit: int
    pytest_summary: str
    ruff_exit: int
    ruff_diagnostics: int
    ruff_rule_counts: dict[str, int]
    mypy_exit: int
    mypy_errors: int
    compileall_exit: int
    diff_check_exit: int
    ruff_signatures: list[str]
    mypy_signatures: list[str]


def _run(
    name: str,
    command: list[str],
    cwd: Path,
    output_dir: Path,
    env: dict[str, str],
) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout_file = output_dir / f"{name}.stdout"
    stderr_file = output_dir / f"{name}.stderr"
    stdout_file.write_text(completed.stdout, encoding="utf-8")
    stderr_file.write_text(completed.stderr, encoding="utf-8")
    (output_dir / f"{name}.command").write_text(
        " ".join(command) + "\n", encoding="utf-8"
    )
    return CommandResult(
        name=name,
        command=command,
        exit_code=completed.returncode,
        stdout_file=str(stdout_file),
        stderr_file=str(stderr_file),
    )


def parse_ruff_output(raw: str, repository: Path) -> tuple[list[str], dict[str, int]]:
    try:
        diagnostics = json.loads(raw)
    except json.JSONDecodeError:
        return [], {"UNPARSEABLE": 1}
    signatures: list[str] = []
    rule_counts: Counter[str] = Counter()
    for diagnostic in diagnostics:
        filename = Path(str(diagnostic.get("filename", "")))
        try:
            relative_file = filename.resolve().relative_to(repository.resolve()).as_posix()
        except ValueError:
            relative_file = filename.as_posix()
        code = str(diagnostic.get("code", "UNKNOWN"))
        message = str(diagnostic.get("message", ""))
        signatures.append(f"{relative_file}|{code}|{message}")
        rule_counts[code] += 1
    return sorted(signatures), dict(sorted(rule_counts.items()))


def parse_mypy_output(raw: str, repository: Path) -> list[str]:
    signatures: list[str] = []
    for line in raw.splitlines():
        match = MYPY_ERROR_RE.match(line.strip())
        if not match:
            continue
        filename = Path(match.group("file"))
        try:
            relative_file = filename.resolve().relative_to(repository.resolve()).as_posix()
        except ValueError:
            relative_file = filename.as_posix()
        code = match.group("code") or "UNCODED"
        signatures.append(f"{relative_file}|{code}|{match.group('message')}")
    return sorted(signatures)


def pytest_summary(raw: str) -> str:
    for line in reversed(raw.splitlines()):
        if " passed" in line or " failed" in line or " error" in line:
            return line.strip()
    return "NO_SUMMARY"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _command_result(results: list[CommandResult], name: str) -> CommandResult:
    for result in results:
        if result.name == name:
            return result
    raise KeyError(name)


def capture_snapshot(
    *,
    label: str,
    repository: Path,
    output_dir: Path,
    python_bin: Path,
    extra_env: dict[str, str] | None = None,
) -> tuple[QualitySnapshot, list[CommandResult]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        **(extra_env or {}),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    results = [
        _run("python_version", [str(python_bin), "--version"], repository, output_dir, environment),
        _run("pytest", [str(python_bin), "-m", "pytest", "-q"], repository, output_dir, environment),
        _run(
            "ruff",
            [str(python_bin), "-m", "ruff", "check", "app", "tests", "--output-format=json"],
            repository,
            output_dir,
            environment,
        ),
        _run("mypy", [str(python_bin), "-m", "mypy", "app"], repository, output_dir, environment),
        _run(
            "compileall",
            [str(python_bin), "-m", "compileall", "-q", "app", "tests"],
            repository,
            output_dir,
            environment,
        ),
        _run("diff_check", ["git", "diff", "--check"], repository, output_dir, environment),
        _run("revision", ["git", "rev-parse", "HEAD"], repository, output_dir, environment),
    ]
    version_raw = "\n".join(
        (
            _read_text(output_dir / "python_version.stdout"),
            _read_text(output_dir / "python_version.stderr"),
        )
    )
    version_match = PYTHON_VERSION_RE.search(version_raw)
    revision = _read_text(output_dir / "revision.stdout").strip()
    ruff_raw = _read_text(output_dir / "ruff.stdout")
    ruff_signatures, ruff_rule_counts = parse_ruff_output(ruff_raw, repository)
    mypy_raw = _read_text(output_dir / "mypy.stdout")
    snapshot = QualitySnapshot(
        label=label,
        repository=str(repository),
        revision=revision,
        python_version=version_match.group("version") if version_match else "UNKNOWN",
        pytest_exit=_command_result(results, "pytest").exit_code,
        pytest_summary=pytest_summary(_read_text(output_dir / "pytest.stdout")),
        ruff_exit=_command_result(results, "ruff").exit_code,
        ruff_diagnostics=len(ruff_signatures),
        ruff_rule_counts=ruff_rule_counts,
        mypy_exit=_command_result(results, "mypy").exit_code,
        mypy_errors=len(parse_mypy_output(mypy_raw, repository)),
        compileall_exit=_command_result(results, "compileall").exit_code,
        diff_check_exit=_command_result(results, "diff_check").exit_code,
        ruff_signatures=ruff_signatures,
        mypy_signatures=parse_mypy_output(mypy_raw, repository),
    )
    (output_dir / "snapshot.json").write_text(
        json.dumps(asdict(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "commands.json").write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return snapshot, results


def compare_snapshots(base: QualitySnapshot, current: QualitySnapshot) -> dict[str, Any]:
    base_ruff = set(base.ruff_signatures)
    current_ruff = set(current.ruff_signatures)
    base_mypy = set(base.mypy_signatures)
    current_mypy = set(current.mypy_signatures)
    return {
        "ruff": {
            "base": base.ruff_diagnostics,
            "current": current.ruff_diagnostics,
            "existing": len(base_ruff & current_ruff),
            "new": sorted(current_ruff - base_ruff),
            "fixed": sorted(base_ruff - current_ruff),
        },
        "mypy": {
            "base": base.mypy_errors,
            "current": current.mypy_errors,
            "existing": len(base_mypy & current_mypy),
            "new": sorted(current_mypy - base_mypy),
            "fixed": sorted(base_mypy - current_mypy),
        },
        "behavior": {
            "base_pytest_exit": base.pytest_exit,
            "current_pytest_exit": current.pytest_exit,
            "base_compileall_exit": base.compileall_exit,
            "current_compileall_exit": current.compileall_exit,
        },
    }


def _add_detached_worktree(repository: Path, base_ref: str, target: Path) -> None:
    completed = subprocess.run(
        ["git", "worktree", "add", "--detach", str(target), base_ref],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git worktree add failed")


def _remove_worktree(repository: Path, target: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(target)],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--alembic", type=Path)
    parser.add_argument("--expected-python", default="3.12")
    parser.add_argument("--fail-on-new", action="store_true")
    args = parser.parse_args()

    repository = args.repository.resolve()
    output = args.output.resolve()
    current_dir = output / "current"
    base_dir = output / "base"
    output.mkdir(parents=True, exist_ok=True)
    extra_env = {}
    if args.alembic:
        extra_env["ALEMBIC_BIN"] = str(args.alembic.resolve())
    base_worktree = Path(tempfile.mkdtemp(prefix="orderai-quality-base-"))
    try:
        _add_detached_worktree(repository, args.base_ref, base_worktree)
        base_snapshot, base_commands = capture_snapshot(
            label="base",
            repository=base_worktree,
            output_dir=base_dir,
            python_bin=args.python,
            extra_env=extra_env,
        )
        current_snapshot, current_commands = capture_snapshot(
            label="current",
            repository=repository,
            output_dir=current_dir,
            python_bin=args.python,
            extra_env=extra_env,
        )
    finally:
        _remove_worktree(repository, base_worktree)
        shutil.rmtree(base_worktree, ignore_errors=True)

    comparison = compare_snapshots(base_snapshot, current_snapshot)
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": str(repository),
        "base_ref": args.base_ref,
        "expected_python_prefix": args.expected_python,
        "base": asdict(base_snapshot),
        "current": asdict(current_snapshot),
        "comparison": comparison,
        "commands": {
            "base": [asdict(result) for result in base_commands],
            "current": [asdict(result) for result in current_commands],
        },
        "classification": (
            "NEW_QUALITY_FAILURES"
            if comparison["ruff"]["new"] or comparison["mypy"]["new"]
            else "BASELINE_REPRODUCED"
        ),
    }
    (output / "baseline-lock.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "classification": result["classification"],
        "base_revision": base_snapshot.revision,
        "current_revision": current_snapshot.revision,
        "base_ruff": base_snapshot.ruff_diagnostics,
        "current_ruff": current_snapshot.ruff_diagnostics,
        "base_mypy": base_snapshot.mypy_errors,
        "current_mypy": current_snapshot.mypy_errors,
        "base_pytest": base_snapshot.pytest_summary,
        "current_pytest": current_snapshot.pytest_summary,
        "output": str(output),
    }, ensure_ascii=False))
    python_ok = base_snapshot.python_version.startswith(args.expected_python) and current_snapshot.python_version.startswith(args.expected_python)
    behavior_ok = all(
        value == 0
        for value in (
            base_snapshot.pytest_exit,
            current_snapshot.pytest_exit,
            base_snapshot.compileall_exit,
            current_snapshot.compileall_exit,
            current_snapshot.diff_check_exit,
        )
    )
    if not python_ok or not behavior_ok:
        return 1
    if args.fail_on_new and result["classification"] != "BASELINE_REPRODUCED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
