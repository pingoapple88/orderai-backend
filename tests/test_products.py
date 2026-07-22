"""WO-006 商品型錄 + 別名比對測試。

涵蓋派工單 §4.1 的 8 個必測 case：
  完全比對 / 別名 / 全形 / 未命中回 None / A 店不得命中 B 店 /
  重複品名 409 / 軟刪除後不出現 / price_cents 非整數 422。

DB：沿用既有測試作法，SessionLocal / TestClient 直打 orderai 庫（已 alembic upgrade head）。
每個測試自建 store + product，結束清理，冪等。
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models import AuditLog, Plan, Product, Store, User
from app.services import product_service

_MARK = "WO006_TEST"  # 用於清理的識別
_LINE = "Uwo006_test_owner"

# 建立 store → user，寫入 audit 需真實 user_id（audit_logs.user_id FK → users.id）。
# 用可變容器讓測試函式取得 fixture 建立的 user id。
_ctx: dict = {}


def _cleanup():
    db = SessionLocal()
    try:
        store_ids = db.execute(
            select(Store.id).where(Store.name.like(f"{_MARK}%"))
        ).scalars().all()
        if store_ids:
            # 依 FK 順序：audit_logs → products → users → stores
            db.execute(delete(AuditLog).where(AuditLog.store_id.in_(store_ids)))
            db.execute(delete(Product).where(Product.store_id.in_(store_ids)))
            db.execute(delete(User).where(User.store_id.in_(store_ids)))
            db.execute(delete(Store).where(Store.id.in_(store_ids)))
        db.execute(delete(User).where(User.line_id == _LINE))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def catalog():
    """建 A/B 兩店 + A 店 owner；A 店有『高麗菜』（別名 包心菜/高麗）。回傳 (store_a_id, store_b_id)。"""
    _cleanup()
    db = SessionLocal()
    try:
        plan_id = db.execute(select(Plan.id).order_by(Plan.id)).scalars().first()
        a = Store(name=f"{_MARK}_A", market="tw")
        b = Store(name=f"{_MARK}_B", market="tw")
        db.add_all([a, b])
        db.flush()
        owner = User(line_id=_LINE, name=f"{_MARK}_owner", plan_id=plan_id, store_id=a.id, role="owner")
        db.add(owner)
        db.flush()
        db.add(Product(store_id=a.id, name="高麗菜", aliases=["高麗", "包心菜", "捲心菜"],
                       unit="顆", price_cents=4500, is_active=True))
        db.add(Product(store_id=b.id, name="雞蛋", aliases=["蛋"],
                       unit="盒", price_cents=6000, is_active=True))
        db.commit()
        _ctx["user_id"] = owner.id
        ids = (a.id, b.id)
    finally:
        db.close()
    yield ids
    _cleanup()


def _principal_token(store_id: int) -> dict:
    tok = create_access_token(
        {"user_id": _ctx.get("user_id", 1), "store_id": store_id, "role": "owner"}
    )
    return {"Authorization": f"Bearer {tok}"}


# ── match_product：§4.1 case 1-5 ──────────────────────────────────────────────

def test_case1_exact_name(catalog):
    """case 1：完全比對『高麗菜』→ 命中。"""
    store_a, _ = catalog
    db = SessionLocal()
    try:
        p = product_service.match_product(db, store_a, "高麗菜")
        assert p is not None and p.price_cents == 4500
    finally:
        db.close()


def test_case2_alias(catalog):
    """case 2：別名比對『包心菜』→ 命中。"""
    store_a, _ = catalog
    db = SessionLocal()
    try:
        p = product_service.match_product(db, store_a, "包心菜")
        assert p is not None and p.name == "高麗菜"
    finally:
        db.close()


def test_case3_fullwidth_and_space(catalog):
    """case 3：全形 + 空白『高　麗　菜』→ 正規化後命中。"""
    store_a, _ = catalog
    db = SessionLocal()
    try:
        p = product_service.match_product(db, store_a, "高　麗　菜")
        assert p is not None and p.name == "高麗菜"
    finally:
        db.close()


def test_case4_unmatched_returns_none(catalog):
    """case 4：未登錄品名『火龍果』→ 回 None，不得猜。"""
    store_a, _ = catalog
    db = SessionLocal()
    try:
        assert product_service.match_product(db, store_a, "火龍果") is None
    finally:
        db.close()


def test_case5_tenant_isolation(catalog):
    """case 5（租戶隔離核心）：A 店的『高麗菜』不得被 B 店命中 → None。"""
    _, store_b = catalog
    db = SessionLocal()
    try:
        assert product_service.match_product(db, store_b, "高麗菜") is None
        # 反向確認 B 店自己的品項仍可命中，證明查詢有效而非全空
        assert product_service.match_product(db, store_b, "雞蛋") is not None
    finally:
        db.close()


# ── CRUD API：§4.1 case 6-8 ───────────────────────────────────────────────────

def test_case6_duplicate_name_409(catalog):
    """case 6：同店重複品名建立 → 409。"""
    store_a, _ = catalog
    client = TestClient(app)
    r = client.post(f"/api/v1/stores/{store_a}/products",
                    headers=_principal_token(store_a),
                    json={"name": "高麗菜", "unit": "顆", "priceCents": 4500})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "CONFLICT"


def test_case7_soft_delete_hidden_from_active_list(catalog):
    """case 7：軟刪除後不出現在 is_active=true 列表。"""
    store_a, _ = catalog
    client = TestClient(app)
    h = _principal_token(store_a)
    # 找到高麗菜 id
    active = client.get(f"/api/v1/stores/{store_a}/products?is_active=true", headers=h).json()["data"]
    pid = next(p["id"] for p in active if p["name"] == "高麗菜")
    # 軟刪除
    dr = client.delete(f"/api/v1/stores/{store_a}/products/{pid}", headers=h)
    assert dr.status_code == 204
    # 不再出現在 active 列表
    active2 = client.get(f"/api/v1/stores/{store_a}/products?is_active=true", headers=h).json()["data"]
    assert all(p["id"] != pid for p in active2)
    # 但實體仍在（is_active=false 可查到）
    db = SessionLocal()
    try:
        p = db.get(Product, pid)
        assert p is not None and p.is_active is False
    finally:
        db.close()


def test_case8_non_integer_price_422(catalog):
    """case 8：price_cents 傳入非整數 → 422（Pydantic 驗證）。"""
    store_a, _ = catalog
    client = TestClient(app)
    r = client.post(f"/api/v1/stores/{store_a}/products",
                    headers=_principal_token(store_a),
                    json={"name": "地瓜", "unit": "斤", "priceCents": 45.5})
    assert r.status_code == 422, r.text


# ── 額外：跨租戶 403（沿用既有 verify_store_access）───────────────────────────

def test_cross_tenant_list_403(catalog):
    """持 A 店 JWT 讀 B 店型錄 → 403（既有 deps.py 行為）。"""
    store_a, store_b = catalog
    client = TestClient(app)
    r = client.get(f"/api/v1/stores/{store_b}/products", headers=_principal_token(store_a))
    assert r.status_code == 403
