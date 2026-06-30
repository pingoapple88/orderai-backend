"""system_settings 讀取（PR-2：參數禁止寫死）。
正式可在前面加 Redis 快取；此處提供 DB 讀取 + 安全預設 fallback。
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.models import SystemSetting


def get_setting(db: Session, key: str, default: Optional[str] = None) -> Optional[str]:
    # 支援 SQLAlchemy Session（db.get）與測試 stub（db.get）兩種模式
    try:
        row = db.get(SystemSetting, key)
    except Exception:
        # fallback: 若 db 不支援 get()，改用 query()
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        except Exception:
            return default
    return row.value if row else default


def get_int_setting(db: Session, key: str, default: int = 0) -> int:
    val = get_setting(db, key)
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default
