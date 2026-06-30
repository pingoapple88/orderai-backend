"""AI 解析服務（情境二：成本防護）。

- pre_filter：呼叫 LLM 前先用 system_settings 的正則判斷是否為接單訊息。
- soft limit：Pro 方案當月超過 ai_soft_limit_pro 即阻斷。
"""
import re
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AIUsageLog, User
from app.services.settings_service import get_int_setting, get_setting


def is_order_message(db: Session, text: str) -> bool:
    """前置意圖預檢：符合接單正則才回 True（否則略過 LLM、不扣額）。"""
    if not text or not text.strip():
        return False
    pattern = get_setting(db, "pre_filter_regex")
    if not pattern:
        return True  # 無設定時保守放行
    try:
        return re.search(pattern, text) is not None
    except re.error:
        return True  # 正則壞掉時 fail-open（避免擋住正常接單）


def monthly_usage(db: Session, user_id: int) -> int:
    first_of_month = date.today().replace(day=1)
    stmt = select(func.coalesce(func.sum(AIUsageLog.usage_count), 0)).where(
        AIUsageLog.user_id == user_id, AIUsageLog.usage_date >= first_of_month
    )
    return int(db.execute(stmt).scalar_one())


def check_soft_limit(db: Session, user: "User") -> tuple[bool, int, int]:
    """回傳 (是否放行, 當月用量, 上限)。Pro 方案套軟限制；其餘走方案硬額度由他處控管。"""
    limit = get_int_setting(db, "ai_soft_limit_pro", 10000)
    used = monthly_usage(db, user.id)
    return used < limit, used, limit
