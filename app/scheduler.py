"""簡易排程：付款未回調主動輪詢（情境四）。

正式可換 APScheduler / cron。此處提供可被單元測試的 reconcile 函式 + 迴圈。
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import AuditLog, BillingRecord
from app.providers import get_payment_provider
from app.services.settings_service import get_int_setting

settings = get_settings()


async def reconcile_pending_payments(db) -> int:
    """對逾時未回調的 pending 帳務，主動向 StallPay 查詢並更新。回傳更新筆數。"""
    interval = get_int_setting(db, "polling_interval_minutes", 30)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=interval)
    provider = get_payment_provider()

    rows = db.execute(
        select(BillingRecord).where(
            BillingRecord.status == "pending", BillingRecord.created_at <= cutoff
        )
    ).scalars().all()

    updated = 0
    for rec in rows:
        result = await provider.get_status(str(rec.id))
        if result.status != rec.status:
            old = rec.status
            rec.status = result.status
            db.add(AuditLog(user_id=rec.user_id, tenant_id=rec.tenant_id,
                            action="payment.reconcile", resource_type="billing_record",
                            resource_id=rec.id, old_value={"status": old},
                            new_value={"status": result.status}))
            updated += 1
    db.commit()
    return updated


def main() -> None:
    while True:
        db = SessionLocal()
        try:
            asyncio.run(reconcile_pending_payments(db))
        finally:
            db.close()
        time.sleep(300)


if __name__ == "__main__":
    main()
