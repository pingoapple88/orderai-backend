"""訂單服務（律三：tenant_id + user_id 雙重隔離；律四：audit）。"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models import AuditLog, Order, OrderItem
from app.services.tax import compute_tax


def _audit(db: Session, principal: dict, action: str, resource_id: Optional[int],
           old=None, new=None) -> None:
    db.add(AuditLog(
        user_id=principal.get("user_id"),
        tenant_id=principal.get("tenant_id"),
        action=action, resource_type="order", resource_id=resource_id,
        old_value=old, new_value=new,
    ))


def _order_number(db: Session) -> str:
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y%m%d")
    cnt = db.execute(
        select(func.count(Order.id)).where(Order.order_number.like(f"OA-{date_part}-%"))
    ).scalar_one()
    return f"OA-{date_part}-{cnt + 1:04d}"


def create_order(db: Session, principal: dict, data: dict) -> Order:
    items = data.get("items", [])
    subtotal_sum = sum(int(i["quantity"]) * int(i["unit_price"]) for i in items)
    market = data.get("market", "tw")
    tax = compute_tax(subtotal_sum, market)          # 情境三：一次性計稅
    total = subtotal_sum + tax

    order = Order(
        user_id=principal["user_id"],
        tenant_id=principal.get("tenant_id"),
        order_number=_order_number(db),
        customer_name=data.get("customer_name"),
        customer_phone=data.get("customer_phone"),
        customer_email=data.get("customer_email"),
        total_amount=total,
        currency=data.get("currency", "TWD"),
        status="pending",
        channel=data.get("channel"),
        notes=data.get("notes"),
    )
    db.add(order)
    db.flush()
    for i in items:
        q, up = int(i["quantity"]), int(i["unit_price"])
        db.add(OrderItem(order_id=order.id, product_name=i.get("product_name"),
                         quantity=q, unit_price=up, subtotal=q * up))
    _audit(db, principal, "order.create", order.id, new={"total_amount": total, "tax": tax})
    db.commit()
    db.refresh(order)
    event_bus.publish("order.created", {"order_id": order.id, "tenant_id": order.tenant_id})
    return order


def list_orders(db: Session, principal: dict, *, page=1, limit=20, status=None):
    where = [Order.tenant_id == principal.get("tenant_id"),
             Order.user_id == principal["user_id"], Order.status != "deleted"]
    if status:
        where.append(Order.status == status)
    total = db.execute(select(func.count(Order.id)).where(*where)).scalar_one()
    rows = db.execute(
        select(Order).where(*where).order_by(Order.created_at.desc())
        .limit(limit).offset((page - 1) * limit)
    ).scalars().all()
    return rows, total


def get_order(db: Session, principal: dict, order_id: int) -> Optional[Order]:
    return db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.tenant_id == principal.get("tenant_id"),
            Order.user_id == principal["user_id"],
            Order.status != "deleted",
        )
    ).scalar_one_or_none()


def update_order(db: Session, principal: dict, order_id: int, updates: dict) -> Optional[Order]:
    order = get_order(db, principal, order_id)
    if not order:
        return None
    old = {"status": order.status, "notes": order.notes}
    for f in ("status", "notes", "customer_name", "customer_phone"):
        if f in updates and updates[f] is not None:
            setattr(order, f, updates[f])
    _audit(db, principal, "order.update", order.id, old=old,
           new={k: updates.get(k) for k in updates})
    db.commit()
    db.refresh(order)
    event_bus.publish("order.updated", {"order_id": order.id, "tenant_id": order.tenant_id})
    return order
