"""WO-04 ENG-01 + company_id 最小硬化：草稿 → 確認 / 退回 三結果 + 律三租戶隔離。

- service 層走 db_session（orderai_drift_test，隔離、可重跑）。
- route 層走 TestClient（SessionLocal → orderai 庫）。
律三：退回由 store_id 推導 company_id（null → fail-closed），雙鍵範圍過濾，跨租戶不可退回/寫 audit。
狀態邊界：僅 pending_confirm 可退回。金額整數分（律七）；退回不刪單、不扣庫、不轉 ERP。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models import AuditLog, Company, Order, OrderItem, Plan, Store, User
from app.services import order_service

_MARK = "REJECT_TEST"


# ── service 層（db_session）──────────────────────────────────────────────────
def _seed_store_owner(db, *, company=True):
    plan = Plan(name="lite", channel="direct", monthly_price=0)
    db.add(plan); db.flush()
    comp_id = None
    if company:
        comp = Company(name="退回測試公司"); db.add(comp); db.flush()
        comp_id = comp.id
    store = Store(name="退回測試店", industry_type="ecom", market="tw", company_id=comp_id)
    db.add(store); db.flush()
    owner = User(line_id="Uowner_rej", name="老闆", role="owner",
                 store_id=store.id, plan_id=plan.id)
    db.add(owner); db.flush(); db.commit()
    return store, owner


def _make_draft(db, principal):
    return order_service.create_order(db, principal, {
        "items": [{"product_name": "蘋果", "quantity": 1, "unit_price": 4500}],
        "customer_name": "王小明", "channel": "line", "line_event_id": None,
    })


def test_draft_confirm_reject_trio(db_session):
    store, owner = _seed_store_owner(db_session)
    principal = {"user_id": owner.id, "store_id": store.id}

    draft = _make_draft(db_session, principal)
    assert draft.status == "pending_confirm"

    confirmed = order_service.confirm_order(db_session, principal, store.id, draft.id)
    assert confirmed.status == "confirmed" and confirmed.confirmed_at is not None

    draft2 = _make_draft(db_session, principal)
    rejected = order_service.reject_order(db_session, principal, store.id, draft2.id, "客戶臨時取消")
    assert rejected.status == "rejected"
    assert "[退回] 客戶臨時取消" in (rejected.notes or "")

    # 稽核帶 store_id + company_id（律四 + 律三）
    row = db_session.execute(
        select(AuditLog).where(AuditLog.resource_id == draft2.id, AuditLog.action == "order.reject")
    ).scalars().first()
    assert row is not None
    assert row.store_id == store.id
    assert row.new_value.get("company_id") == store.company_id


def test_reject_missing_order_returns_none(db_session):
    store, owner = _seed_store_owner(db_session)
    principal = {"user_id": owner.id, "store_id": store.id}
    assert order_service.reject_order(db_session, principal, store.id, 999999, "x") is None


def test_reject_only_pending_confirm_service(db_session):
    """狀態邊界:僅 pending_confirm 可退回;confirmed/completed/cancelled 不可,原狀態不變。"""
    store, owner = _seed_store_owner(db_session)
    principal = {"user_id": owner.id, "store_id": store.id}
    d = _make_draft(db_session, principal)
    order_service.confirm_order(db_session, principal, store.id, d.id)
    with pytest.raises(ValueError):
        order_service.reject_order(db_session, principal, store.id, d.id, "x")
    assert db_session.get(Order, d.id).status == "confirmed"
    for st in ("completed", "cancelled"):
        d2 = _make_draft(db_session, principal)
        order_service.update_order(db_session, principal, store.id, d2.id, {"status": st})
        with pytest.raises(ValueError):
            order_service.reject_order(db_session, principal, store.id, d2.id, "x")
        assert db_session.get(Order, d2.id).status == st


def test_reject_null_company_id_fail_closed(db_session):
    """律三:store.company_id 為 null → fail-closed(PermissionError),訂單不變、不寫 reject audit。"""
    store, owner = _seed_store_owner(db_session, company=False)   # company_id = None
    principal = {"user_id": owner.id, "store_id": store.id}
    draft = _make_draft(db_session, principal)
    with pytest.raises(PermissionError):
        order_service.reject_order(db_session, principal, store.id, draft.id, "x")
    assert db_session.get(Order, draft.id).status == "pending_confirm"
    acts = db_session.execute(
        select(AuditLog.action).where(AuditLog.action == "order.reject")
    ).scalars().all()
    assert "order.reject" not in acts


def test_reject_nonexistent_store_fail_closed(db_session):
    """律三:store 不存在 → fail-closed,不猜測、不補預設。"""
    store, owner = _seed_store_owner(db_session)
    draft = _make_draft(db_session, {"user_id": owner.id, "store_id": store.id})
    with pytest.raises(PermissionError):
        order_service.reject_order(db_session, {"user_id": owner.id, "store_id": store.id + 999},
                                   store.id + 999, draft.id, "x")
    assert db_session.get(Order, draft.id).status == "pending_confirm"


def test_reject_cross_company_blocked(db_session):
    """律三:store_B/company_2 principal 不可退回 store_A/company_1 的訂單(雙鍵 miss → None),不變、無 audit。"""
    plan = Plan(name="lite", channel="direct", monthly_price=0); db_session.add(plan); db_session.flush()
    c1 = Company(name="c1"); c2 = Company(name="c2"); db_session.add_all([c1, c2]); db_session.flush()
    sa = Store(name="A", industry_type="ecom", market="tw", company_id=c1.id)
    sb = Store(name="B", industry_type="ecom", market="tw", company_id=c2.id)
    db_session.add_all([sa, sb]); db_session.flush()
    ua = User(line_id="ua", name="a", role="owner", store_id=sa.id, plan_id=plan.id)
    ub = User(line_id="ub", name="b", role="owner", store_id=sb.id, plan_id=plan.id)
    db_session.add_all([ua, ub]); db_session.flush(); db_session.commit()
    order = order_service.create_order(
        db_session, {"user_id": ua.id, "store_id": sa.id},
        {"items": [{"product_name": "蘋果", "quantity": 1, "unit_price": 4500}], "channel": "line"})
    res = order_service.reject_order(
        db_session, {"user_id": ub.id, "store_id": sb.id}, sb.id, order.id, "x")
    assert res is None
    assert db_session.get(Order, order.id).status == "pending_confirm"
    acts = db_session.execute(
        select(AuditLog.action).where(AuditLog.resource_id == order.id, AuditLog.action == "order.reject")
    ).scalars().all()
    assert "order.reject" not in acts


# ── route 層（TestClient / SessionLocal）─────────────────────────────────────
@pytest.fixture()
def http_seed():
    db = SessionLocal()
    _cleanup(db)
    plan = Plan(name=f"{_MARK}_plan", channel="direct", monthly_price=0)
    db.add(plan); db.flush()
    comp_a = Company(name=f"{_MARK}_compA"); comp_b = Company(name=f"{_MARK}_compB")
    db.add_all([comp_a, comp_b]); db.flush()
    store_a = Store(name=f"{_MARK}_A", industry_type="ecom", market="tw", company_id=comp_a.id)
    store_b = Store(name=f"{_MARK}_B", industry_type="ecom", market="tw", company_id=comp_b.id)
    db.add_all([store_a, store_b]); db.flush()
    owner = User(line_id=f"{_MARK}_owner", name="老闆", role="owner",
                 store_id=store_a.id, plan_id=plan.id)
    db.add(owner); db.flush()
    order = Order(user_id=owner.id, store_id=store_a.id, order_number=f"{_MARK}-1",
                  total_cents=4500, currency="TWD", status="pending_confirm", channel="line")
    db.add(order); db.flush(); db.commit()
    ids = {"store_a": store_a.id, "store_b": store_b.id, "owner": owner.id, "order": order.id}
    db.close()
    yield ids
    db2 = SessionLocal(); _cleanup(db2); db2.close()


def _cleanup(db):
    sids = db.execute(select(Store.id).where(Store.name.like(f"{_MARK}%"))).scalars().all()
    if sids:
        db.execute(delete(AuditLog).where(AuditLog.store_id.in_(sids)))
        db.execute(delete(OrderItem).where(
            OrderItem.order_id.in_(select(Order.id).where(Order.store_id.in_(sids)))))
        db.execute(delete(Order).where(Order.store_id.in_(sids)))
        db.execute(delete(User).where(User.store_id.in_(sids)))
        db.execute(delete(Store).where(Store.id.in_(sids)))
    db.execute(delete(Company).where(Company.name.like(f"{_MARK}%")))
    db.execute(delete(Plan).where(Plan.name.like(f"{_MARK}%")))
    db.commit()


def _hdr(user_id, store_id):
    return {"Authorization": "Bearer " + create_access_token({"user_id": user_id, "store_id": store_id})}


def test_route_reject_200(http_seed):
    c = TestClient(app)
    r = c.post(f"/api/v1/stores/{http_seed['store_a']}/orders/{http_seed['order']}/reject",
               headers=_hdr(http_seed["owner"], http_seed["store_a"]),
               json={"reason": "缺商品名"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "rejected"


def test_route_reject_cross_store_403(http_seed):
    c = TestClient(app)
    r = c.post(f"/api/v1/stores/{http_seed['store_a']}/orders/{http_seed['order']}/reject",
               headers=_hdr(http_seed["owner"], http_seed["store_b"]),
               json={"reason": "x"})
    assert r.status_code == 403


def test_route_reject_non_draft_409(http_seed):
    """已確認訂單退回 → 409,狀態維持 confirmed(狀態邊界)。"""
    c = TestClient(app)
    h = _hdr(http_seed["owner"], http_seed["store_a"])
    cf = c.post(f"/api/v1/stores/{http_seed['store_a']}/orders/{http_seed['order']}/confirm", headers=h)
    assert cf.status_code == 200 and cf.json()["data"]["status"] == "confirmed"
    r = c.post(f"/api/v1/stores/{http_seed['store_a']}/orders/{http_seed['order']}/reject",
               headers=h, json={"reason": "x"})
    assert r.status_code == 409, r.text
    g = c.get(f"/api/v1/stores/{http_seed['store_a']}/orders/{http_seed['order']}", headers=h)
    assert g.json()["data"]["status"] == "confirmed"
