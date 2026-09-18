"""Focused tests for the reusable provider-neutral ERP conformance harness."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from app.core.interfaces.erp_conformance import (
    ErpPendingOrderConformanceMixin,
    PendingOrderConformancePlan,
    public_conformance_evidence,
    run_pending_order_conformance,
)
from app.core.interfaces.erp_traceability import build_pending_order_trace_manifest
from app.providers.jiezhou_erp import FakeJiezhouErpIngestProvider, JiezhouBlockedErpIngestProvider
from scripts.jiezhou_contract_smoke import (
    DEFAULT_FIXTURE_PATH,
    build_provider_neutral_contract,
    load_synthetic_fixture,
)
from scripts.jiezhou_erp_conformance import (
    build_jiezhou_fake_conformance_plan,
    main,
    run_jiezhou_fake_conformance,
)


def _jiezhou_fake_plan() -> PendingOrderConformancePlan:
    return build_jiezhou_fake_conformance_plan()


class TestJiezhouFakeConformance(ErpPendingOrderConformanceMixin):
    """Example future ERP fake/sandbox tests can reuse without changing its adapter API."""

    def build_pending_order_conformance_plan(self) -> PendingOrderConformancePlan:
        return _jiezhou_fake_plan()

    def test_fake_satisfies_all_controlled_pending_intent_cases(self):
        evidence = self.assert_pending_order_conformance()
        records = public_conformance_evidence(evidence)

        assert len(records) == 6
        assert {frozenset(record) for record in records} == {
            frozenset({"contract_version", "hash", "status", "reason_code", "counts"})
        }
        assert {record["status"] for record in records} == {"blocked", "manual_review", "pending"}
        assert {record["reason_code"] for record in records} == {
            None,
            "ERP_CONNECTION_BLOCKED",
            "ERP_PRODUCT_MAPPING_MISSING",
            "ERP_TIMEOUT",
            "ERP_UNKNOWN_RESPONSE",
        }
        assert {record["hash"] for record in records} == {records[0]["hash"]}
        assert all(len(record["hash"]) == 64 for record in records)
        assert records[2]["counts"] == {"attempts": 1, "replays": 0, "transaction_side_effects": 0}
        assert records[3]["counts"] == {"attempts": 2, "replays": 1, "transaction_side_effects": 0}
        assert all(record["counts"].get("transaction_side_effects", 0) == 0 for record in records)


def test_jiezhou_fake_cli_example_is_strictly_redacted_and_writes_same_json(tmp_path, monkeypatch, capsys):
    evidence_path = tmp_path / "jiezhou-conformance.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "jiezhou_erp_conformance.py",
            "--fixture",
            str(DEFAULT_FIXTURE_PATH),
            "--output",
            str(evidence_path),
        ],
    )

    assert main() == 0
    printed = json.loads(capsys.readouterr().out)
    written = json.loads(evidence_path.read_text())
    assert printed == written == run_jiezhou_fake_conformance()

    fixture = load_synthetic_fixture(DEFAULT_FIXTURE_PATH)
    serialized = json.dumps(printed, ensure_ascii=False, sort_keys=True)
    for raw_value in (
        fixture["intent"]["content"]["buyer_name"],
        fixture["intent"]["content"]["buyer_contact_reference"],
        fixture["intent"]["content"]["requested_for"],
        fixture["intent"]["content"]["special_request"],
        fixture["intent"]["source_event_id"],
        fixture["intent"]["idempotency_key"],
        fixture["intent"]["audit_reference"],
        *fixture["intent"]["product_mapping"].keys(),
        *fixture["intent"]["product_mapping"].values(),
    ):
        assert raw_value not in serialized


def test_harness_rejects_manifest_not_bound_to_the_same_pending_order_intent():
    fixture = load_synthetic_fixture(DEFAULT_FIXTURE_PATH)
    config, intent = build_provider_neutral_contract(fixture)
    mismatched_manifest = build_pending_order_trace_manifest(
        replace(intent, source_event_id="synthetic-event-other"),
        contract_version=config.contract_reference,
    )
    plan = replace(_jiezhou_fake_plan(), manifest=mismatched_manifest)

    with pytest.raises(ValueError, match="ERP_TRACE_INTENT_SHA256_MISMATCH"):
        run_pending_order_conformance(plan)


def test_harness_rejects_exposed_nonzero_transaction_side_effects():
    fixture = load_synthetic_fixture(DEFAULT_FIXTURE_PATH)
    config, intent = build_provider_neutral_contract(fixture)

    class SideEffectingFake(FakeJiezhouErpIngestProvider):
        @property
        def transaction_side_effects(self):
            return ("not-a-transaction-record",)

    plan = PendingOrderConformancePlan(
        contract_version=config.contract_reference,
        intent=intent,
        blocked_provider=JiezhouBlockedErpIngestProvider,
        manual_review_provider=lambda: FakeJiezhouErpIngestProvider(replace(config, product_mapping={})),
        pending_provider=lambda: SideEffectingFake(config),
        timeout_provider=lambda: FakeJiezhouErpIngestProvider(
            config, outcome_by_source_event={intent.source_event_id: "timeout"}
        ),
        unknown_provider=lambda: FakeJiezhouErpIngestProvider(
            config, outcome_by_source_event={intent.source_event_id: "unknown"}
        ),
        manual_review_reason_code="ERP_PRODUCT_MAPPING_MISSING",
    )

    with pytest.raises(AssertionError, match="ERP_CONFORMANCE_TRANSACTION_SIDE_EFFECTS_NONZERO"):
        run_pending_order_conformance(plan)


def test_public_evidence_never_includes_provider_names_or_references():
    serialized = json.dumps(run_jiezhou_fake_conformance(), ensure_ascii=False, sort_keys=True)
    assert "jiezhou_fake" not in serialized
    assert "jz-pending-" not in serialized
    assert "jz-manual-" not in serialized
