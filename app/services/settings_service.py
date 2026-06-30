"""system_settings 讀取（PR-2：參數禁止寫死）。

正式可在前面加 Redis 快取；此處提供 DB 讀取 + 安全預設 fallback。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SystemSetting

# 僅作為「DB 尚無該 key」時的最後防線，非業務寫死值
_FALLBACK = {
    "ai_soft_limit_pro": "10000",
    "pre_filter_regex": r"(\+\s*\d+|＋\s*\d+|#下單|要買|預購|下單|訂購|\d+\s*份|\d+\s*個|\d+\s*組)",
    "polling_interval_minutes": "30",
}


def get_setting(db: Session, key: str, default: Optional[str] = None) -> Optional[str]:
    row = db.get(SystemSetting, key)
    if row and row.value is not None:
        return row.value
    return default if default is not None else _FALLBACK.get(key)


def get_int_setting(db: Session, key: str, default: int) -> int:
    val = get_setting(db, key, str(default))
    try:
        return int(val)
    except (TypeError, ValueError):
        return default
