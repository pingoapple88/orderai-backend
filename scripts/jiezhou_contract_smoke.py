#!/usr/bin/env python3
"""Offline smoke evidence for the Jiezhou synthetic pending-order contract.

This CLI deliberately reads only the tracked synthetic fixture and exercises the
provider-neutral ``PendingOrderIntent`` with the deterministic in-memory fake.
It has no endpoint, credentials, transport, database, or external I/O.  The
formal provider is checked separately through its factory and must remain
``ERP_CONNECTION_BLOCKED`` until a written Jiezhou contract and sandbox exist.

Examples:
    python scripts/jiezhou_contract_smoke.py
    python scripts/jiezhou_contract_smoke.py --output /tmp/jiezhou-smoke.json --pretty
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator, Mapping

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "jiezhou_pending_order_contract_v1.json"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.core.interfaces.erp_ingest import (  # noqa: E402
    ErpIngestBlockedError,
    ErpIngestResult,
    PendingOrderContent,
    PendingOrderIntent,
    PendingOrderItem,
    PendingOrderMappingConfig,
)
from app.core.interfaces.erp_traceability import (  # noqa: E402
    build_pending_order_trace_manifest,
    pending_order_trace_validation_reason,
)
from app.providers import get_jiezhou_erp_ingest_provider, settings  # noqa: E402
from app.providers.jiezhou_erp import FakeJiezhouErpIngestProvider  # noqa: E402


Evidence = dict[str, Any]


def load_synthetic_fixture(path: Path) -> dict[str, Any]:
    """Load the explicitly supplied synthetic contract fixture; never fetch data."""

    with path.open(encoding="utf-8") as fixture_file:
        data = json.load(fixture_file)
    if not isinstance(data, dict):
        raise ValueError("synthetic fixture must be a JSON object")
    return data


def build_provider_neutral_contract(
    fixture: Mapping[str, Any],
) -> tuple[PendingOrderMappingConfig, PendingOrderIntent]:
    """Build neutral contract types without assuming any Jiezhou formal fields."""

    mapping_config = fixture["mapping_config"]
    raw_intent = fixture["intent"]
    content = raw_intent["content"]
    config = PendingOrderMappingConfig(**mapping_config)
    intent = PendingOrderIntent(
        tenant_id=raw_intent["tenant_id"],
        company_id=raw_intent["company_id"],
        sales_location_id=raw_intent["sales_location_id"],
        source_event_id=raw_intent["source_event_id"],
        content=PendingOrderContent(
            buyer_name=content["buyer_name"],
            buyer_contact_reference=content["buyer_contact_reference"],
            requested_for=content["requested_for"],
            special_request=content["special_request"],
            items=[PendingOrderItem(**item) for item in content["items"]],
        ),
        product_mapping=raw_intent["product_mapping"],
        idempotency_key=raw_intent["idempotency_key"],
        audit_reference=raw_intent["audit_reference"],
    )
    return config, intent


def _require_result(
    name: str,
    result: ErpIngestResult,
    *,
    expected_status: str,
    expected_reason_code: str | None,
) -> Evidence:
    """Assert a controlled outcome and return a safe, result-only evidence record."""

    if result.status != expected_status or result.reason_code != expected_reason_code:
        raise AssertionError(
            f"{name}: expected ({expected_status}, {expected_reason_code}), "
            f"got ({result.status}, {result.reason_code})"
        )
    return {
        "name": name,
        "expected_status": expected_status,
        "status": result.status,
        "reason_code": result.reason_code,
    }


@contextmanager
def _synthetic_formal_factory_settings(config: PendingOrderMappingConfig) -> Iterator[None]:
    """Temporarily select formal Jiezhou mode using only this synthetic fixture.

    The factory must still return its blocked implementation.  Values are restored
    so importing and reusing this CLI cannot mutate caller configuration.
    """

    attribute_values = {
        "jiezhou_erp_ingest_provider": "jiezhou",
        "jiezhou_tenant_id": config.tenant_id,
        "jiezhou_company_id": config.company_id,
        "jiezhou_sales_location_id": config.sales_location_id,
        "jiezhou_product_mapping_json": json.dumps(config.product_mapping, sort_keys=True),
        "jiezhou_contract_reference": config.contract_reference,
    }
    original_values = {name: getattr(settings, name) for name in attribute_values}
    try:
        for name, value in attribute_values.items():
            setattr(settings, name, value)
        yield
    finally:
        for name, value in original_values.items():
            setattr(settings, name, value)


def _verify_formal_provider_is_blocked(
    config: PendingOrderMappingConfig, intent: PendingOrderIntent
) -> Evidence:
    """Exercise the real factory without adding a formal transport or request schema."""

    with _synthetic_formal_factory_settings(config):
        provider = get_jiezhou_erp_ingest_provider()
        try:
            asyncio.run(provider.submit_pending_confirmation_intent(intent))
        except ErpIngestBlockedError as exc:
            if exc.reason_code != "ERP_CONNECTION_BLOCKED":
                raise AssertionError(f"formal provider returned {exc.reason_code}, not ERP_CONNECTION_BLOCKED") from exc
        else:
            raise AssertionError("formal Jiezhou provider must fail closed")

    return {
        "provider": provider.name,
        "status": "blocked",
        "reason_code": "ERP_CONNECTION_BLOCKED",
    }


def _assert_evidence_has_no_fixture_content(evidence: Evidence, intent: PendingOrderIntent) -> None:
    """Prevent direct customer, request, mapping, or identifier data from evidence."""

    serialized_evidence = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    content_values = [
        intent.content.buyer_name,
        intent.content.buyer_contact_reference,
        intent.content.requested_for,
        intent.content.special_request,
        intent.source_event_id,
        intent.idempotency_key,
        intent.audit_reference,
        *intent.product_mapping.keys(),
        *intent.product_mapping.values(),
        *(item.product_name for item in intent.content.items),
        *(item.source_product_key for item in intent.content.items),
    ]
    for value in content_values:
        if value and str(value) in serialized_evidence:
            raise AssertionError("evidence must not contain raw fixture content")


def run_contract_smoke(fixture_path: Path = DEFAULT_FIXTURE_PATH) -> Evidence:
    """Run deterministic pending/manual-review cases and return JSON-safe evidence."""

    fixture = load_synthetic_fixture(fixture_path)
    config, intent = build_provider_neutral_contract(fixture)
    trace_manifest = build_pending_order_trace_manifest(
        intent,
        contract_version=config.contract_reference,
    )
    if (
        pending_order_trace_validation_reason(
            intent,
            contract_version=config.contract_reference,
            manifest=trace_manifest,
        )
        is not None
    ):
        raise AssertionError("trace manifest must verify against its source intent")

    pending_provider = FakeJiezhouErpIngestProvider(mapping_config=config)
    pending_result = asyncio.run(pending_provider.submit_pending_confirmation_intent(intent))
    replay_result = asyncio.run(pending_provider.submit_pending_confirmation_intent(intent))
    if pending_result.reference != replay_result.reference or len(pending_provider.recorded_intents) != 1:
        raise AssertionError("replay must return the original pending result without a second recorded intent")

    scenarios = [
        _require_result("pending", pending_result, expected_status="pending", expected_reason_code=None),
        _require_result("replay", replay_result, expected_status="pending", expected_reason_code=None),
    ]

    missing_mapping = asyncio.run(
        FakeJiezhouErpIngestProvider(mapping_config=config).submit_pending_confirmation_intent(
            replace(intent, product_mapping={})
        )
    )
    scenarios.append(
        _require_result(
            "missing_mapping",
            missing_mapping,
            expected_status="manual_review",
            expected_reason_code="ERP_PRODUCT_MAPPING_MISSING",
        )
    )

    scope_mismatch = asyncio.run(
        FakeJiezhouErpIngestProvider(mapping_config=config).submit_pending_confirmation_intent(
            replace(intent, company_id=intent.company_id + 1)
        )
    )
    scenarios.append(
        _require_result(
            "scope_mismatch",
            scope_mismatch,
            expected_status="manual_review",
            expected_reason_code="ERP_COMPANY_SCOPE_MISMATCH",
        )
    )

    for outcome, reason_code in (("timeout", "ERP_TIMEOUT"), ("unknown", "ERP_UNKNOWN_RESPONSE")):
        result = asyncio.run(
            FakeJiezhouErpIngestProvider(
                mapping_config=config,
                outcome_by_source_event={intent.source_event_id: outcome},
            ).submit_pending_confirmation_intent(intent)
        )
        scenarios.append(
            _require_result(
                outcome,
                result,
                expected_status="manual_review",
                expected_reason_code=reason_code,
            )
        )

    if pending_provider.transaction_side_effects != ():
        raise AssertionError("synthetic fake must not create transaction side effects")

    evidence: Evidence = {
        "tool": "jiezhou_contract_smoke",
        "execution_mode": "offline_synthetic_no_transport",
        "fixture_version": fixture["fixture_version"],
        "contract_status": fixture["contract_status"],
        "trace_manifest": trace_manifest.comparison_evidence(),
        "formal_provider": _verify_formal_provider_is_blocked(config, intent),
        "scenarios": scenarios,
        "assertions": {
            "all_passed": True,
            "network_calls": 0,
            "transaction_side_effects": 0,
            "replay_reference_matches": True,
        },
    }
    _assert_evidence_has_no_fixture_content(evidence, intent)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run offline Jiezhou synthetic contract smoke checks and emit JSON-safe evidence."
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

    evidence = run_contract_smoke(args.fixture)
    serialized = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        indent=2 if args.pretty else None,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
