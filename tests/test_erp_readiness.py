"""Focused coverage for the additive, provider-neutral ERP readiness manifest."""
from __future__ import annotations

import json
import socket

import pytest

from app.core.interfaces.erp_ingest import ErpIngestBlockedError
from app.core.interfaces.erp_readiness import (
    ERP_READINESS_MANIFEST_VERSION,
    ErpReadinessDeclaration,
    ErpReadinessMode,
    build_erp_delivery_readiness_manifest,
    public_erp_delivery_readiness_evidence,
)
from scripts.erp_readiness_manifest import main, run_readiness_evidence


_REQUIRED_BOOLEAN_FIELDS = {
    "contract_version_supported",
    "mapping_complete",
    "tenant_scope_bound",
    "sales_location_scope_bound",
    "transport_configured",
    "formal_delivery_enabled",
    "conformance_passed",
}


def _fully_reviewed_declaration(mode: ErpReadinessMode) -> ErpReadinessDeclaration:
    """Safe boolean-only declaration; it intentionally contains no config values."""

    return ErpReadinessDeclaration(
        mode=mode,
        contract_version_supported=True,
        mapping_complete=True,
        tenant_scope_bound=True,
        sales_location_scope_bound=True,
        transport_configured=True,
        conformance_passed=True,
        formal_delivery_authorized=True,
    )


def test_default_unknown_manifest_is_fail_closed_with_required_safe_booleans():
    manifest = build_erp_delivery_readiness_manifest()
    evidence = public_erp_delivery_readiness_evidence(manifest)

    assert manifest.manifest_version == ERP_READINESS_MANIFEST_VERSION
    assert all(evidence[field] is False for field in _REQUIRED_BOOLEAN_FIELDS)
    assert "ERP_CONNECTION_BLOCKED" in evidence["reason_codes"]
    assert set(evidence) == {
        "manifest_version",
        *_REQUIRED_BOOLEAN_FIELDS,
        "reason_codes",
        "network_calls",
    }
    assert evidence["network_calls"] == 0

    with pytest.raises(ErpIngestBlockedError) as exc:
        manifest.require_formal_delivery()
    assert exc.value.reason_code == "ERP_CONNECTION_BLOCKED"


def test_unknown_and_formal_jiezhou_cannot_override_transport_or_formal_delivery():
    for mode in (ErpReadinessMode.UNKNOWN, ErpReadinessMode.JIEZHOU_FORMAL):
        manifest = build_erp_delivery_readiness_manifest(_fully_reviewed_declaration(mode))

        assert manifest.contract_version_supported is True
        assert manifest.mapping_complete is True
        assert manifest.tenant_scope_bound is True
        assert manifest.sales_location_scope_bound is True
        assert manifest.conformance_passed is True
        assert manifest.transport_configured is False
        assert manifest.formal_delivery_enabled is False
        assert manifest.reason_codes == ("ERP_CONNECTION_BLOCKED",)


def test_synthetic_fake_can_report_conformance_without_enabling_formal_delivery():
    manifest = build_erp_delivery_readiness_manifest(
        ErpReadinessDeclaration.synthetic(
            contract_version_supported=True,
            mapping_complete=True,
            tenant_scope_bound=True,
            sales_location_scope_bound=True,
            conformance_passed=True,
        )
    )

    assert manifest.conformance_passed is True
    assert manifest.transport_configured is False
    assert manifest.formal_delivery_enabled is False
    assert manifest.reason_codes == ("ERP_CONNECTION_BLOCKED",)


def test_declared_cloudding_and_future_formal_provider_can_report_a_reviewed_ready_state():
    for mode in (ErpReadinessMode.CLOUD_DING, ErpReadinessMode.FUTURE_FORMAL):
        manifest = build_erp_delivery_readiness_manifest(_fully_reviewed_declaration(mode))

        assert all(
            getattr(manifest, field)
            for field in _REQUIRED_BOOLEAN_FIELDS
        )
        assert manifest.reason_codes == ()
        manifest.require_formal_delivery()


def test_manifest_never_reads_provider_or_network_configuration(monkeypatch):
    def fail_connect(*args, **kwargs):
        raise AssertionError("readiness manifest must not open a network connection")

    monkeypatch.setattr(socket.socket, "connect", fail_connect)
    manifest = build_erp_delivery_readiness_manifest(
        ErpReadinessDeclaration(
            mode=ErpReadinessMode.CLOUD_DING,
            contract_version_supported=True,
            mapping_complete=True,
            tenant_scope_bound=True,
            sales_location_scope_bound=True,
            transport_configured=False,
            conformance_passed=True,
        )
    )

    evidence = public_erp_delivery_readiness_evidence(manifest)
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    assert "endpoint" not in serialized
    assert "secret" not in serialized
    assert "tenant-" not in serialized
    assert evidence["network_calls"] == 0


def test_readiness_cli_emits_value_free_offline_evidence_and_writes_same_json(tmp_path, monkeypatch, capsys):
    evidence_path = tmp_path / "erp-readiness.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "erp_readiness_manifest.py",
            "--scenario",
            "jiezhou-fake",
            "--output",
            str(evidence_path),
        ],
    )

    assert main() == 0
    printed = json.loads(capsys.readouterr().out)
    written = json.loads(evidence_path.read_text())

    assert printed == written == run_readiness_evidence("jiezhou-fake")
    assert printed["conformance_passed"] is True
    assert printed["transport_configured"] is False
    assert printed["formal_delivery_enabled"] is False
    assert printed["reason_codes"] == ["ERP_CONNECTION_BLOCKED"]
    assert printed["network_calls"] == 0
    assert "jiezhou" not in json.dumps(printed, ensure_ascii=False, sort_keys=True).lower()


@pytest.mark.parametrize("scenario", ["unknown", "jiezhou-formal", "cloud-ding", "future-formal"])
def test_cli_scenarios_stay_fail_closed_without_reviewed_sensitive_configuration(scenario):
    evidence = run_readiness_evidence(scenario)

    assert evidence["transport_configured"] is False
    assert evidence["formal_delivery_enabled"] is False
    assert "ERP_CONNECTION_BLOCKED" in evidence["reason_codes"]
    assert evidence["network_calls"] == 0
