#!/usr/bin/env python3
"""Emit offline, value-free ERP delivery readiness evidence.

This CLI is intentionally a declaration example, not a configuration probe.  It
never imports application settings, constructs a provider, reads an endpoint,
authentication value, secret, or identifier, and never opens a network
connection.  Provider owners supply reviewed booleans to the helper in their
pre-submission path; the built-in scenarios demonstrate the safe default and a
synthetic fake conformance result.

Examples:
    python scripts/erp_readiness_manifest.py --scenario unknown --pretty
    python scripts/erp_readiness_manifest.py --scenario jiezhou-fake --pretty
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.core.interfaces.erp_readiness import (  # noqa: E402
    ErpReadinessDeclaration,
    ErpReadinessMode,
    build_erp_delivery_readiness_manifest,
    public_erp_delivery_readiness_evidence,
)


_SCENARIOS = frozenset({"unknown", "cloud-ding", "jiezhou-formal", "jiezhou-fake", "future-formal"})


def _declaration_for_scenario(scenario: str) -> ErpReadinessDeclaration:
    """Return only fixed safe booleans; no scenario reads real configuration."""

    if scenario == "unknown":
        return ErpReadinessDeclaration()
    if scenario == "jiezhou-fake":
        # A passed fake conformance run demonstrates only synthetic readiness;
        # policy still blocks a real transport and any formal delivery.
        return ErpReadinessDeclaration.synthetic(
            contract_version_supported=True,
            mapping_complete=True,
            tenant_scope_bound=True,
            sales_location_scope_bound=True,
            conformance_passed=True,
        )
    if scenario == "cloud-ding":
        return ErpReadinessDeclaration(mode=ErpReadinessMode.CLOUD_DING)
    if scenario == "jiezhou-formal":
        return ErpReadinessDeclaration(mode=ErpReadinessMode.JIEZHOU_FORMAL)
    if scenario == "future-formal":
        return ErpReadinessDeclaration(mode=ErpReadinessMode.FUTURE_FORMAL)
    raise ValueError("ERP_READINESS_SCENARIO_INVALID")


def run_readiness_evidence(scenario: str = "unknown") -> dict[str, object]:
    """Build strict public evidence for a local, fixed capability scenario."""

    return public_erp_delivery_readiness_evidence(
        build_erp_delivery_readiness_manifest(_declaration_for_scenario(scenario))
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit offline, value-free ERP delivery readiness evidence."
    )
    parser.add_argument("--scenario", choices=sorted(_SCENARIOS), default="unknown")
    parser.add_argument("--output", type=Path, help="optional local JSON evidence file")
    parser.add_argument("--pretty", action="store_true", help="indent JSON evidence")
    args = parser.parse_args()

    evidence = run_readiness_evidence(args.scenario)
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
