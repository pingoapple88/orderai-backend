from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult
from app.models import AuditLog, Plan, Product, Store, User
from app.services import order_risk_service, product_service


def _seed(db):
    plan = Plan(name="test", channel="direct", monthly_price=0)
    db.add(plan)
    db.flush()
    store = Store(name="風險測試店", industry_type="ecom", market="tw")
    db.add(store)
    db.flush()
    owner = User(line_id="Uriskowner", name="店主", role="owner", store_id=store.id, plan_id=plan.id)
    product = Product(store_id=store.id, name="高麗菜", aliases=["高麗"], unit="顆", price_cents=4500)
    db.add_all([owner, product])
    db.commit()
    return store, owner


def _result(*, confidence=0.9, product_name="高麗菜", qty=2, evidence="高麗菜2顆"):
    return ExtractionResult(
        items=[ExtractedItem(product_name=product_name, quantity=qty, evidence=evidence, confidence_score=confidence)],
        confidence_score=confidence,
        provider_name="test",
        industry_type="ecom",
    )


def test_matching_high_confidence_extraction_is_approved(db_session):
    store, _ = _seed(db_session)
    result = _result()
    priced = product_service.price_extracted_items(db_session, store.id, result.items)

    decision = order_risk_service.evaluate_order_extraction(
        db_session, result, priced, default_threshold=0.85
    )

    assert decision.status == "approved"
    assert decision.reasons == []
    assert decision.threshold == 0.85


def test_unmatched_catalog_product_requires_human_review(db_session):
    store, _ = _seed(db_session)
    result = _result(product_name="不存在商品")
    priced = product_service.price_extracted_items(db_session, store.id, result.items)

    decision = order_risk_service.evaluate_order_extraction(
        db_session, result, priced, default_threshold=0.85
    )

    assert decision.status == "needs_review"
    assert "catalog_product_unmatched" in decision.reasons


def test_low_confidence_requires_human_review(db_session):
    store, _ = _seed(db_session)
    result = _result(confidence=0.84)
    priced = product_service.price_extracted_items(db_session, store.id, result.items)

    decision = order_risk_service.evaluate_order_extraction(
        db_session, result, priced, default_threshold=0.85
    )

    assert decision.status == "needs_review"
    assert "confidence_below_threshold" in decision.reasons


def test_threshold_boundary_086_is_approved(db_session):
    store, _ = _seed(db_session)
    result = _result(confidence=0.86)
    priced = product_service.price_extracted_items(db_session, store.id, result.items)

    decision = order_risk_service.evaluate_order_extraction(
        db_session, result, priced, default_threshold=0.85
    )

    assert decision.status == "approved"
    assert decision.reasons == []


def test_audit_log_contains_hash_not_original_line_content(db_session):
    store, owner = _seed(db_session)
    result = _result()
    decision = order_risk_service.RiskDecision("approved", [], 0.85)

    order_risk_service.audit_ai_decision(
        db_session,
        principal={"user_id": owner.id, "store_id": store.id},
        extraction=result,
        decision=decision,
        source_text="我是王阿姨 高麗菜2顆 電話0912345678 email@example.com",
    )

    log = db_session.query(AuditLog).filter(AuditLog.action == "ai.order.decision").one()
    assert log.new_value["status"] == "approved"
    assert log.new_value["source_sha256"]
    assert "0912345678" not in str(log.new_value)
    assert "email@example.com" not in str(log.new_value)
    assert "王阿姨" not in str(log.new_value)
