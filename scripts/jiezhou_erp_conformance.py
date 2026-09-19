#!/usr/bin/env python3
"""Run the generic ERP conformance harness against the synthetic Jiezhou fake.

This is an offline example for fake/sandbox adapter authors.  It loads only the
tracked synthetic fixture, uses no formal endpoint/authentication/transport, and
never changes provider factories.  Its JSON output is a strict PII-safe list whose
records contain only contract version, manifest hash, status, reason code, and
numeric counts.

Examples:
    python scripts/jiezhou_erp_conformance.py
    python scripts/jiezhou_erp_conformance.py --output /tmp/jiezhou-conformance.json --pretty
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.core.interfaces.erp_conformance import (  # noqa: E402
    PendingOrderConformancePlan,
    public_conformance_evidence,
    run_pending_order_conformance,
)
from app.providers.jiezhou_erp import (  # noqa: E402
    FakeJiezhouErpIngestProvider,
    JiezhouBlockedErpIngestProvider,
)
from scripts.jiezhou_contract_smoke import (  # noqa: E402
    DEFAULT_FIXTURE_PATH,
    build_provider_neutral_contract,
    load_synthetic_fixture,
)


def build_jiezhou_fake_conformance_plan(fixture_path: Path = DEFAULT_FIXTURE_PATH) -> PendingOrderConformancePlan:
    """Build a six-scenario plan with one intent and one verified trace manifest.

    The manual-review case changes only the fake's local mapping configuration; the
    intent is unchanged for all six calls.  Timeout and unknown are deterministic
    fake outcomes and remain manual review, never formal transactions.
    """

    fixture: dict[str, Any] = load_synthetic_fixture(fixture_path)
    config, intent = build_provider_neutral_contract(fixture)
    manual_review_config = replace(config, product_mapping={})

    return PendingOrderConformancePlan(
        contract_version=config.contract_reference,
        intent=intent,
        blocked_provider=JiezhouBlockedErpIngestProvider,
        manual_review_provider=lambda: FakeJiezhouErpIngestProvider(manual_review_config),
        pending_provider=lambda: FakeJiezhouErpIngestProvider(config),
        timeout_provider=lambda: FakeJiezhouErpIngestProvider(
            config,
            outcome_by_source_event={intent.source_event_id: "timeout"},
        ),
        unknown_provider=lambda: FakeJiezhouErpIngestProvider(
            config,
            outcome_by_source_event={intent.source_event_id: "unknown"},
        ),
        manual_review_reason_code="ERP_PRODUCT_MAPPING_MISSING",
    )


def run_jiezhou_fake_conformance(fixture_path: Path = DEFAULT_FIXTURE_PATH) -> list[dict[str, object]]:
    """Return only the generic harness's strict public evidence records."""

    plan = build_jiezhou_fake_conformance_plan(fixture_path)
    return public_conformance_evidence(run_pending_order_conformance(plan))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run offline Jiezhou fake ERP conformance checks with PII-safe JSON output."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="path to a local synthetic contract fixture (default: tracked Jiezhou fixture)",
    )
    parser.add_argument("--output", type=Path, help="optional local JSON evidence file")
    parser.add_argument("--pretty", action="store_true", help="indent JSON evidence")
    args = parser.parse_args()

    evidence = run_jiezhou_fake_conformance(args.fixture)
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
