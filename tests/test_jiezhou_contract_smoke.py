"""Focused tests for the offline Jiezhou synthetic contract smoke CLI."""
import json
from pathlib import Path

from scripts.jiezhou_contract_smoke import DEFAULT_FIXTURE_PATH, main, run_contract_smoke


def test_smoke_runner_emits_redacted_expected_controlled_outcomes():
    evidence = run_contract_smoke()

    outcomes = {scenario["name"]: scenario for scenario in evidence["scenarios"]}
    assert {name: outcome["status"] for name, outcome in outcomes.items()} == {
        "pending": "pending",
        "replay": "pending",
        "missing_mapping": "manual_review",
        "scope_mismatch": "manual_review",
        "timeout": "manual_review",
        "unknown": "manual_review",
    }
    assert outcomes["missing_mapping"]["reason_code"] == "ERP_PRODUCT_MAPPING_MISSING"
    assert outcomes["scope_mismatch"]["reason_code"] == "ERP_COMPANY_SCOPE_MISMATCH"
    assert outcomes["timeout"]["reason_code"] == "ERP_TIMEOUT"
    assert outcomes["unknown"]["reason_code"] == "ERP_UNKNOWN_RESPONSE"
    assert evidence["formal_provider"] == {
        "provider": "jiezhou_blocked",
        "status": "blocked",
        "reason_code": "ERP_CONNECTION_BLOCKED",
    }
    assert evidence["assertions"] == {
        "all_passed": True,
        "network_calls": 0,
        "transaction_side_effects": 0,
        "replay_reference_matches": True,
    }

    fixture = json.loads(DEFAULT_FIXTURE_PATH.read_text())
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    assert fixture["intent"]["content"]["buyer_name"] not in serialized
    assert fixture["intent"]["audit_reference"] not in serialized
    assert fixture["intent"]["idempotency_key"] not in serialized


def test_smoke_cli_writes_json_evidence(tmp_path, monkeypatch, capsys):
    evidence_path = tmp_path / "jiezhou-contract-smoke.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "jiezhou_contract_smoke.py",
            "--fixture",
            str(DEFAULT_FIXTURE_PATH),
            "--output",
            str(evidence_path),
        ],
    )

    assert main() == 0
    printed = json.loads(capsys.readouterr().out)
    written = json.loads(Path(evidence_path).read_text())
    assert printed == written
    assert written["formal_provider"]["reason_code"] == "ERP_CONNECTION_BLOCKED"
