"""商品型錄服務（WO-006）。律三：所有存取以 store_id 過濾；律四：寫入 audit。

match_product 是本單核心：抄單抽取的每個品名 → 找店家型錄的價格。
先命中即回，未命中回 None。**不做模糊比對、不猜**——猜錯的價格比沒有價格更糟。
"""
import unicodedata
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditLog, Product


class ProductNameDuplicate(Exception):
    """同店品名重複（違反 UNIQUE(store_id, name)）→ 路由層轉 409 CONFLICT。"""


def _audit(db: Session, principal: dict, action: str, resource_id: Optional[int],
           old=None, new=None) -> None:
    db.add(AuditLog(
        user_id=principal.get("user_id"),
        store_id=principal.get("store_id"),
        action=action, resource_type="product", resource_id=resource_id,
        old_value=old, new_value=new,
    ))


def _normalize(s: str) -> str:
    """正規化 = 全形轉半形（NFKC，含全形數字/英文/空格）+ 去所有空白 + 英文轉小寫。

    NFKC 把全形字元與全形空格(U+3000)一併轉半形，故「高　麗　菜」→「高麗菜」。
    """
    s = unicodedata.normalize("NFKC", s)
    s = "".join(s.split())          # 去所有空白（NFKC 後全形空格已成半形空格）
    return s.lower()


# ── CRUD ────────────────────────────────────────────────────────────────────

def list_products(db: Session, store_id: int, *, is_active: Optional[bool] = None):
    where = [Product.store_id == store_id]           # 律三：租戶隔離
    if is_active is not None:
        where.append(Product.is_active == is_active)
    return db.execute(
        select(Product).where(*where).order_by(Product.name)
    ).scalars().all()


def get_product(db: Session, store_id: int, product_id: int) -> Optional[Product]:
    return db.execute(
        select(Product).where(Product.id == product_id, Product.store_id == store_id)
    ).scalar_one_or_none()


def create_product(db: Session, principal: dict, store_id: int, data: dict) -> Product:
    p = Product(
        store_id=store_id,
        name=data["name"],
        aliases=data.get("aliases", []),
        unit=data["unit"],
        price_cents=int(data["price_cents"]),       # 律七：整數分
        is_active=True,
    )
    db.add(p)
    try:
        db.flush()                                   # 觸發 UNIQUE(store_id, name)
    except IntegrityError:
        db.rollback()
        raise ProductNameDuplicate(data["name"])
    _audit(db, principal, "product.create", p.id, new={"name": p.name, "price_cents": p.price_cents})
    db.commit()
    db.refresh(p)
    return p


def update_product(db: Session, principal: dict, store_id: int, product_id: int,
                   updates: dict) -> Optional[Product]:
    p = get_product(db, store_id, product_id)        # 律三：只在本店範圍找
    if not p:
        return None
    old = {"name": p.name, "price_cents": p.price_cents, "is_active": p.is_active}
    if updates.get("name") is not None:
        p.name = updates["name"]
    if updates.get("aliases") is not None:
        p.aliases = updates["aliases"]
    if updates.get("unit") is not None:
        p.unit = updates["unit"]
    if updates.get("price_cents") is not None:
        p.price_cents = int(updates["price_cents"])
    if updates.get("is_active") is not None:
        p.is_active = bool(updates["is_active"])
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ProductNameDuplicate(updates.get("name"))
    _audit(db, principal, "product.update", p.id, old=old,
           new={"name": p.name, "price_cents": p.price_cents, "is_active": p.is_active})
    db.commit()
    db.refresh(p)
    return p


def soft_delete_product(db: Session, principal: dict, store_id: int, product_id: int) -> bool:
    """軟刪除：is_active=false，不實體刪除（保留已成立訂單的品項參照）。"""
    p = get_product(db, store_id, product_id)
    if not p:
        return False
    if p.is_active:
        p.is_active = False
        _audit(db, principal, "product.delete", p.id, old={"is_active": True}, new={"is_active": False})
        db.commit()
    return True


# ── 別名比對（本單核心）──────────────────────────────────────────────────────

def match_product(db: Session, store_id: int, raw_name: str) -> Optional[Product]:
    """抄單品名 → 店家型錄。先命中即回；未命中回 None，不猜。

    比對順序（僅在 store_id 範圍、僅 is_active）：
      1. name 完全比對
      2. aliases 完全比對
      3. 正規化後比對（去空白 + 全形轉半形 + 小寫）
    """
    if not raw_name:
        return None
    products = db.execute(
        select(Product).where(Product.store_id == store_id, Product.is_active.is_(True))
    ).scalars().all()

    # 1. name 完全比對
    for p in products:
        if p.name == raw_name:
            return p
    # 2. aliases 完全比對
    for p in products:
        if raw_name in (p.aliases or []):
            return p
    # 3. 正規化後比對
    norm = _normalize(raw_name)
    for p in products:
        if _normalize(p.name) == norm:
            return p
        for a in (p.aliases or []):
            if _normalize(a) == norm:
                return p
    return None
