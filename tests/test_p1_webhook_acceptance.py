"""Focused tests for the controlled Qingquangu P1 webhook acceptance tool."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sqlalchemy.orm import sessionmaker

from app.models import Company, Customer, IntakeConversation, LineWebhookEvent, Store
from app.p1_uat_seed import _SYNTHETIC_COMPANY_NAME, _SYNTHETIC_STORE_KEY
from app.p1_webhook_acceptance import P1WebhookAcceptanceBlocked, run_p1_webhook_acceptance


def _configure_local_uat(monkeypatch) -> str:
    secret = "synthetic-test-signing-secret"
    monkeypatch.setenv("ENVIRONMENT", "uat")
    monkeypatch.setenv("P1_UAT_ENVIRONMENT_MARKER", "qingquan-p1-uat")
    monkeypatch.setenv("P1_WEBHOOK_ACCEPTANCE_API_BASE_URL", "http://localhost:8010")
    monkeypatch.setenv("P1_WEBHOOK_ACCEPTANCE_ALLOWED_HOSTS", "localhost")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://uat:masked@localhost:5432/orderai_uat")
    monkeypatch.setenv("P1_WEBHOOK_ACCEPTANCE_DATABASE_HOST", "localhost")
    monkeypatch.setenv("LINE_MESSAGING_CHANNEL_SECRET", secret)
    return secret


def _synthetic_scope(db_session):
    company = Company(name=_SYNTHETIC_COMPANY_NAME)
    db_session.add(company)
    db_session.flush()
    store = Store(
        name="青泉谷 P1 webhook 驗收合成店",
        company_id=company.id,
        store_key=_SYNTHETIC_STORE_KEY,
    )
    db_session.add(store)
    db_session.commit()
    return company, store


def test_acceptance_posts_one_signed_synthetic_webhook_and_replay_with_deidentified_evidence(db_session, monkeypatch):
    secret = _configure_local_uat(monkeypatch)
    company, store = _synthetic_scope(db_session)
    received = []

    def post(url, *, content, headers, timeout):
        assert url == "http://localhost:8010/api/v1/webhooks/line"
        assert timeout == 10.0
        expected = base64.b64encode(hmac.new(secret.encode(), content, hashlib.sha256).digest()).decode()
        assert headers["X-Line-Signature"] == expected
        assert headers["User-Agent"] == "orderai-p1-synthetic-acceptance"
        payload = json.loads(content)
        event_id = payload["events"][0]["webhookEventId"]
        received.append((content, event_id))
        if len(received) == 1:
            event = LineWebhookEvent(
                company_id=company.id,
                store_id=store.id,
                channel="line",
                webhook_event_id=event_id,
                event_type="message",
                message_type="sticker",
                status="processed",
            )
            db_session.add(event)
            db_session.flush()
            db_session.add(IntakeConversation(
                company_id=company.id,
                store_id=store.id,
                source_event_id=event.id,
                source_kind="sticker",
                state="needs_human_review",
            ))
            db_session.commit()
        return SimpleNamespace(status_code=200)

    result = run_p1_webhook_acceptance(
        timeout_seconds=1,
        session_factory=lambda: db_session,
        post=post,
        sleep=lambda _: None,
    )

    assert len(received) == 2
    assert received[0][0] == received[1][0]
    assert result == {
        "action": "p1_webhook_acceptance",
        "synthetic_only": True,
        "event_id_sha256": hashlib.sha256(received[0][1].encode()).hexdigest(),
        "http": {"initial_status": 200, "replay_status": 200},
        "event_ledger": {"count": 1, "status": "processed"},
        "case": {"count": 1, "state": "needs_human_review"},
        "side_effect_counts": {
            "customer": 0,
            "order": 0,
            "payment": 0,
            "inventory": 0,
            "shipment": 0,
            "invoice": 0,
        },
        "side_effect_scope": {
            "customer": "customers",
            "order": "orders",
            "payment": "billing_records",
            "inventory": "inventory_inquiries (manual inquiry only; no reservation/decrement ledger exists)",
            "shipment": "not_modelled_by_this_service",
            "invoice": "not_modelled_by_this_service",
        },
        "replay": {"duplicate_ledger_entries": 0, "duplicate_cases": 0, "not_duplicated": True},
        "passed": True,
    }
    evidence = json.dumps(result, ensure_ascii=False)
    assert secret not in evidence
    assert received[0][1] not in evidence


def test_cli_blocks_without_uat_environment_before_database_initialization(monkeypatch):
    for name in (
        "ENVIRONMENT",
        "P1_UAT_ENVIRONMENT_MARKER",
        "P1_WEBHOOK_ACCEPTANCE_API_BASE_URL",
        "P1_WEBHOOK_ACCEPTANCE_ALLOWED_HOSTS",
        "P1_WEBHOOK_ACCEPTANCE_DATABASE_HOST",
        "LINE_MESSAGING_CHANNEL_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    completed = subprocess.run(
        [sys.executable, "scripts/p1_webhook_acceptance.py", "--run"],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(__import__("os").environ),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert json.loads(completed.stderr) == {
        "blocked": "P1_WEBHOOK_ACCEPTANCE_ENVIRONMENT_NOT_UAT",
        "passed": False,
    }


def test_acceptance_is_safely_repeatable_with_one_fixed_ledger_event_and_case(db_session, monkeypatch):
    secret = _configure_local_uat(monkeypatch)
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False, future=True)
    setup = db_session
    try:
        company, store = _synthetic_scope(setup)
        company_id, store_id = company.id, store.id
    finally:
        setup.expunge_all()
    received = []

    def post(url, *, content, headers, timeout):
        assert url == "http://localhost:8010/api/v1/webhooks/line"
        assert headers["X-Line-Signature"] == base64.b64encode(
            hmac.new(secret.encode(), content, hashlib.sha256).digest()
        ).decode()
        received.append(content)
        event_id = json.loads(content)["events"][0]["webhookEventId"]
        db = Session()
        try:
            if db.query(LineWebhookEvent).filter_by(store_id=store_id, webhook_event_id=event_id).count() == 0:
                event = LineWebhookEvent(
                    company_id=company_id,
                    store_id=store_id,
                    channel="line",
                    webhook_event_id=event_id,
                    event_type="message",
                    message_type="sticker",
                    status="processed",
                )
                db.add(event)
                db.flush()
                db.add(IntakeConversation(
                    company_id=company_id,
                    store_id=store_id,
                    source_event_id=event.id,
                    source_kind="sticker",
                    state="needs_human_review",
                ))
                db.commit()
            return SimpleNamespace(status_code=200)
        finally:
            db.close()

    first = run_p1_webhook_acceptance(
        timeout_seconds=1, session_factory=Session, post=post, sleep=lambda _: None
    )
    second = run_p1_webhook_acceptance(
        timeout_seconds=1, session_factory=Session, post=post, sleep=lambda _: None
    )

    assert first["replay"]["not_duplicated"] is True
    assert second["replay"]["not_duplicated"] is True
    assert first["event_id_sha256"] == second["event_id_sha256"]
    assert len(received) == 4 and len(set(received)) == 1
    check = Session()
    try:
        assert check.query(LineWebhookEvent).filter_by(store_id=store_id, channel="line").count() == 1
        assert check.query(IntakeConversation).filter_by(store_id=store_id).count() == 1
    finally:
        check.close()


@pytest.mark.parametrize(
    ("name", "value", "reason"),
    [
        ("ENVIRONMENT", "production", "P1_WEBHOOK_ACCEPTANCE_PRODUCTION_ENVIRONMENT_REJECTED"),
        ("P1_WEBHOOK_ACCEPTANCE_API_BASE_URL", "https://api.orderai.merchcore.ai", "P1_WEBHOOK_ACCEPTANCE_PRODUCTION_HOST_REJECTED"),
    ],
)
def test_acceptance_rejects_production_environment_or_host_before_any_http_call(monkeypatch, name, value, reason):
    _configure_local_uat(monkeypatch)
    monkeypatch.setenv(name, value)

    def must_not_post(*args, **kwargs):
        raise AssertionError("production guard must block before any HTTP request")

    with pytest.raises(P1WebhookAcceptanceBlocked, match=reason):
        run_p1_webhook_acceptance(post=must_not_post)


def test_acceptance_rejects_missing_explicit_allowlist_before_any_http_call(monkeypatch):
    _configure_local_uat(monkeypatch)
    monkeypatch.delenv("P1_WEBHOOK_ACCEPTANCE_ALLOWED_HOSTS")

    def must_not_post(*args, **kwargs):
        raise AssertionError("allowlist guard must block before any HTTP request")

    with pytest.raises(P1WebhookAcceptanceBlocked, match="P1_WEBHOOK_ACCEPTANCE_ALLOWED_HOSTS_INVALID"):
        run_p1_webhook_acceptance(post=must_not_post)


def test_acceptance_rejects_nonzero_formal_side_effect_baseline_before_any_http_call(db_session, monkeypatch):
    _configure_local_uat(monkeypatch)
    _, store = _synthetic_scope(db_session)
    db_session.add(Customer(store_id=store.id, name="synthetic but forbidden baseline customer"))
    db_session.commit()

    def must_not_post(*args, **kwargs):
        raise AssertionError("baseline must be checked before any HTTP request")

    with pytest.raises(P1WebhookAcceptanceBlocked, match="P1_WEBHOOK_ACCEPTANCE_BASELINE_NOT_EMPTY"):
        run_p1_webhook_acceptance(session_factory=lambda: db_session, post=must_not_post)

