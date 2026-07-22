"""WO-006 §2.4：抽取結果接型錄帶價（price_extracted_items）。

驗證抽單結果能正確帶到價格；未命中兩欄皆 None，不猜。
"""
import pytest
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.interfaces.llm_provider import ExtractedItem
from app.models import Product, Store
from app.services import product_service

_MARK = "WO006_INGEST"


def _cleanup():
    db = SessionLocal()
    try:
        ids = db.execute(select(Store.id).where(Store.name.like(f"{_MARK}%"))).scalars().all()
        if ids:
            db.execute(delete(Product).where(Product.store_id.in_(ids)))
            db.execute(delete(Store).where(Store.id.in_(ids)))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def store_with_catalog():
    _cleanup()
    db = SessionLocal()
    try:
        s = Store(name=f"{_MARK}_A", market="tw")
        db.add(s)
        db.flush()
        db.add(Product(store_id=s.id, name="高麗菜", aliases=["包心菜"],
                       unit="顆", price_cents=4500, is_active=True))
        db.commit()
        sid = s.id
    finally:
        db.close()
    yield sid
    _cleanup()


def test_extracted_items_carry_catalog_price(store_with_catalog):
    """命中型錄的品項帶到正確 unit_price_cents 與 matched_product_id。"""
    store_id = store_with_catalog
    items = [
        ExtractedItem(product_name="高麗菜", quantity=2),   # 完全比對
        ExtractedItem(product_name="包心菜", quantity=1),   # 別名比對
    ]
    db = SessionLocal()
    try:
        priced = product_service.price_extracted_items(db, store_id, items)
    finally:
        db.close()
    assert priced[0]["unit_price_cents"] == 4500
    assert priced[0]["matched_product_id"] is not None
    assert priced[1]["unit_price_cents"] == 4500          # 別名也帶到同一商品的價
    assert priced[0]["matched_product_id"] == priced[1]["matched_product_id"]


def test_unmatched_item_both_null(store_with_catalog):
    """未命中品項：matched_product_id 與 unit_price_cents 皆 None，不猜。"""
    store_id = store_with_catalog
    db = SessionLocal()
    try:
        priced = product_service.price_extracted_items(
            db, store_id, [ExtractedItem(product_name="火龍果", quantity=3)]
        )
    finally:
        db.close()
    assert priced[0]["matched_product_id"] is None
    assert priced[0]["unit_price_cents"] is None


def test_pricing_is_tenant_scoped(store_with_catalog):
    """帶價僅限本店型錄：另一店查同名品也不得帶到本店的價。"""
    _store_a = store_with_catalog
    db = SessionLocal()
    try:
        other = Store(name=f"{_MARK}_B", market="tw")
        db.add(other)
        db.flush()
        priced = product_service.price_extracted_items(
            db, other.id, [ExtractedItem(product_name="高麗菜", quantity=1)]
        )
        db.rollback()
    finally:
        db.close()
    assert priced[0]["matched_product_id"] is None
    assert priced[0]["unit_price_cents"] is None
