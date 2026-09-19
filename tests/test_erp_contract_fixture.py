"""Focused tests for provider-neutral synthetic ERP contract fixture validation."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.core.interfaces.erp_contract_fixture import build_synthetic_pending_order_contract


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "jiezhou_pending_order_contract_v1.json"


def _fixture() -> dict[str, object]:
    return json.loads(_FIXTURE_PATH.read_text())


def test_strict_fixture_validator_builds_the_existing_synthetic_pending_order_contract():
    config, intent = build_synthetic_pending_order_contract(_fixture())

    assert config.validation_reason(intent) is None
    assert intent.content.items[0].source_product_key in config.product_mapping


@pytest.mark.parametrize(
    ("mutate", "expected_reason"),
    [
        (
            lambda fixture: fixture["intent"].update({"payment": {"amount": 1}}),
            "ERP_FIXTURE_TRANSACTION_FIELD_FORBIDDEN",
        ),
        (
            lambda fixture: fixture["intent"]["content"].update({"invoice": "synthetic"}),
            "ERP_FIXTURE_TRANSACTION_FIELD_FORBIDDEN",
        ),
        (
            lambda fixture: fixture["intent"].update({"company_id": fixture["intent"]["company_id"] + 1}),
            "ERP_COMPANY_SCOPE_MISMATCH",
        ),
        (
            lambda fixture: fixture["intent"].update({"product_mapping": {}}),
            "ERP_FIXTURE_SCHEMA_INVALID",
        ),
        (
            lambda fixture: fixture.update({"fixture_version": "formal-contract-v1"}),
            "ERP_FIXTURE_NOT_SYNTHETIC",
        ),
        (
            lambda fixture: fixture.update({"contract_status": "approved"}),
            "ERP_FIXTURE_CONTRACT_STATUS_INVALID",
        ),
    ],
)
def test_strict_fixture_validator_fail_closed_for_contract_drift(mutate, expected_reason):
    fixture = deepcopy(_fixture())
    mutate(fixture)

    with pytest.raises(ValueError) as exc:
        build_synthetic_pending_order_contract(fixture)

    assert str(exc.value) == expected_reason
    assert "Synthetic Buyer" not in str(exc.value)
    assert "jiezhou" not in str(exc.value).lower()


def test_strict_fixture_validator_rejects_unknown_fields_at_every_contract_boundary():
    fixture = _fixture()
    fixture["intent"]["content"]["unreviewed_extension"] = "ignored by a loose loader"

    with pytest.raises(ValueError, match="ERP_FIXTURE_SCHEMA_INVALID"):
        build_synthetic_pending_order_contract(fixture)
