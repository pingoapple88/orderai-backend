"""Regression tests for LINE worker fail-closed P1 intake boundaries.

These tests use the migrated PostgreSQL fixture and synthetic data only. They
ensure a worker invocation cannot bypass the signed P1 event ledger or restore
the legacy direct Customer/Order path.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult
from app.models import Company, Customer, IntakeConversation, Order, Plan, Product, Store
from app.workers import line_worker


class _FakeLLM:
    async def extract_order(self, text=None, image_url=None, industry_type="ecom"):
        return ExtractionResult(
            items=[
                ExtractedItem(
                    product_name="蘋果",
                    quantity=3,
                    evidence="蘋果 x3",
                    confidence_score=0.99,
                )
            ],
            customer_name="合成買方",
            confidence_score=0.99,
            industry_type="ecom",
            raw={
                "requested_for": "2026-09-20T02:00:00+00:00",
                "special_request": "合成特別要求",
            },
        )


class _FakeNotif:
    async def send_message(self, to, text, reply_token=None):
        raise AssertionError("an unledgered event must not receive a sale acknowledgement")


def _seed(db):
    company = Company(name="Ledger gate synthetic company")
    plan = Plan(name="ledger-gate", channel="direct", monthly_price=0)
    db.add_all([company, plan])
    db.flush()
    store = Store(name="Ledger gate synthetic store", company_id=company.id, industry_type="ecom", market="tw")
    db.add(store)
    db.flush()
    db.add(Product(store_id=store.id, name="蘋果", aliases=[], unit="顆", price_cents=4500))
    db.commit()
    return store


def _payload():
    return {
        "events": [
            {
                "type": "message",
                "webhookEventId": "unledgered-high-confidence-event",
                "source": {"type": "user", "userId": "Usynthetic"},
                "message": {"type": "text", "id": "synthetic-message", "text": "蘋果 x3"},
            }
        ]
    }


def _count(db, model):
    return db.execute(select(func.count(model.id))).scalar_one()


def test_high_confidence_event_not_present_in_p1_ledger_fails_closed_without_formal_records(db_session, monkeypatch):
    store = _seed(db_session)
    monkeypatch.setattr(line_worker.settings, "p1_intake_enabled", True)
    monkeypatch.setattr(line_worker.settings, "default_store_id", store.id)
    monkeypatch.setattr("app.providers.get_llm_provider", _FakeLLM)
    monkeypatch.setattr("app.providers.get_notification_provider", _FakeNotif)

    asyncio.run(line_worker.process_webhook_event(_payload(), db=db_session))

    assert _count(db_session, IntakeConversation) == 0
    assert _count(db_session, Customer) == 0
    assert _count(db_session, Order) == 0
