from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.p1_uat_acceptance import P1UatAcceptanceBlocked, _assert_direct_acceptance_target


def test_direct_acceptance_is_disabled_by_default(monkeypatch):
    import app.p1_uat_acceptance as acceptance

    monkeypatch.setattr(acceptance, "settings", SimpleNamespace(
        p1_uat_direct_acceptance_enabled=False,
        p1_intake_enabled=True,
        p1_uat_delivery_enabled=True,
        p1_erp_ingest_provider="http",
    ))
    with pytest.raises(P1UatAcceptanceBlocked, match="P1_UAT_DIRECT_ACCEPTANCE_DISABLED"):
        _assert_direct_acceptance_target()


@pytest.mark.parametrize(
    ("intake_enabled", "delivery_enabled", "provider", "reason"),
    [
        (False, True, "http", "P1_UAT_INTAKE_DISABLED"),
        (True, False, "http", "P1_UAT_DELIVERY_DISABLED"),
        (True, True, "blocked", "P1_UAT_ERP_PROVIDER_NOT_HTTP"),
    ],
)
def test_direct_acceptance_requires_all_explicit_delivery_guards(monkeypatch, intake_enabled, delivery_enabled, provider, reason):
    import app.p1_uat_acceptance as acceptance

    monkeypatch.setattr(acceptance, "settings", SimpleNamespace(
        p1_uat_direct_acceptance_enabled=True,
        p1_intake_enabled=intake_enabled,
        p1_uat_delivery_enabled=delivery_enabled,
        p1_erp_ingest_provider=provider,
    ))
    with pytest.raises(P1UatAcceptanceBlocked, match=reason):
        _assert_direct_acceptance_target()
