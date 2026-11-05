"""WO-L3-001 對話層①：AI 口吻回覆（取代三句罐頭）。

回覆 = 開場白(LLM) + "\\n" + 事實區塊(程式產) + "\\n" + 結尾(LLM)。

邊界：
- 數字 100% 由程式產生：品項、數量、小計、總計只來自型錄帶價結果與訂單 total_cents。
  LLM 只寫兩句話；若 LLM 句子含任何數字或金額符號 → 視為不可信，回退罐頭句。
- LLM 走 ILLMProvider（get_llm_provider() 注入的實例）。provider 需提供
  `compose_reply(outcome=..., brand_voice=...) -> (opening, closing)` 能力；
  未提供、逾時、拋例外、回傳格式不符 → 一律回退罐頭句（fail-safe，不阻斷建單）。
- 不對客人顯示 reason_code（技術碼只寫 audit，由呼叫端負責）。
- 本模組永不拋例外：compose() 一定回字串。
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

from app.core.config import get_settings

logger = logging.getLogger(__name__)

OUTCOME_ORDER_CREATED = "order_created"
OUTCOME_NEEDS_REVIEW = "needs_review"
OUTCOME_PROVIDER_ERROR = "provider_error"
OUTCOMES = (OUTCOME_ORDER_CREATED, OUTCOME_NEEDS_REVIEW, OUTCOME_PROVIDER_ERROR)

# 罐頭句（回退用）。成功句的事實區塊仍由程式產生，故回退時也含品項＋總計。
_CANNED = {
    OUTCOME_ORDER_CREATED: ("已收到您的訂單：", "請稍候店家確認。"),
    OUTCOME_NEEDS_REVIEW: ("收到您的訊息了。", "請稍候，或補充商品名稱與數量。"),
    OUTCOME_PROVIDER_ERROR: ("收到您的訊息了。", "請稍候，店家會盡快回覆您。"),
}

# 非成功情境的核心句（程式產，不交給 LLM）。
_CORE = {
    OUTCOME_NEEDS_REVIEW: "這筆我不太確定，幫您轉給店家人工確認喔。",
    OUTCOME_PROVIDER_ERROR: "系統忙了一下，已請店家協助處理。",
}

# LLM 句子不得含數字（半形、全形、中文數字）或金額符號。
_FORBIDDEN_IN_LLM_LINE = re.compile(r"[0-9０-９$＄元一二三四五六七八九十百千萬兩零〇]")


@dataclass(frozen=True)
class ReplyItem:
    name: str
    qty: int
    unit_price_cents: int


def format_cents(cents: int) -> str:
    """顯示格式化（唯一允許的分→元換算處）。TWD：整數元不顯示小數。"""
    # 唯一例外：顯示格式化。金額內部一律以「分」運算，此處只為顯示將分換成元。
    dollars, rem = divmod(int(cents), 100)
    if rem == 0:
        return "${:,}".format(dollars)
    return "${:,}.{:02d}".format(dollars, rem)


def build_fact_block(items: Sequence[ReplyItem], total_cents: int) -> str:
    """事實區塊：每品項「名稱 x數量  $小計」＋「總計 $xxx」。純程式產生。"""
    lines = [
        "{} x{}  {}".format(i.name, i.qty, format_cents(i.qty * i.unit_price_cents))
        for i in items
    ]
    lines.append("總計 {}".format(format_cents(total_cents)))
    return "\n".join(lines)


def _sanitize_llm_line(line: Any, max_chars: int) -> Optional[str]:
    if not isinstance(line, str):
        return None
    line = " ".join(line.split())
    if not line or len(line) > max_chars:
        return None
    if _FORBIDDEN_IN_LLM_LINE.search(line):
        return None
    return line


async def _llm_lines(llm: Any, outcome: str, brand_voice: str) -> Optional[Tuple[str, str]]:
    settings = get_settings()
    if llm is None or not settings.reply_llm_enabled:
        return None
    compose = getattr(llm, "compose_reply", None)
    if compose is None or not callable(compose):
        return None
    try:
        res = await asyncio.wait_for(
            compose(outcome=outcome, brand_voice=brand_voice),
            timeout=settings.reply_llm_timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — 含逾時；回覆層一律 fail-safe
        logger.warning("reply_composer LLM failed outcome=%s err=%s", outcome, type(exc).__name__)
        return None
    if not isinstance(res, (tuple, list)) or len(res) != 2:
        logger.warning("reply_composer LLM bad shape outcome=%s", outcome)
        return None
    opening = _sanitize_llm_line(res[0], settings.reply_llm_max_chars)
    closing = _sanitize_llm_line(res[1], settings.reply_llm_max_chars)
    if opening is None or closing is None:
        logger.warning("reply_composer LLM line rejected outcome=%s", outcome)
        return None
    return opening, closing


def _assemble(opening: str, body: str, closing: str) -> str:
    return "{}\n{}\n{}".format(opening, body, closing)


async def compose(
    outcome: str,
    *,
    items: Sequence[ReplyItem] = (),
    total_cents: int = 0,
    reason_code: Optional[str] = None,
    llm: Any = None,
    brand_voice: Optional[str] = None,
) -> str:
    """組回覆字串。永不拋例外。reason_code 只供 log，不出現在回覆內容。"""
    if outcome not in OUTCOMES:
        outcome = OUTCOME_PROVIDER_ERROR
    try:
        if outcome == OUTCOME_ORDER_CREATED:
            body = build_fact_block(items, total_cents)
        else:
            body = _CORE[outcome]
    except Exception:  # noqa: BLE001 — 事實資料異常時不可阻斷，退到不含數字的核心句
        logger.exception("reply_composer fact block failed")
        outcome = OUTCOME_NEEDS_REVIEW
        body = _CORE[outcome]

    voice = get_settings().reply_brand_voice if brand_voice is None else brand_voice
    lines = await _llm_lines(llm, outcome, voice or "")
    if lines is None:
        opening, closing = _CANNED[outcome]
    else:
        opening, closing = lines
    if reason_code:
        logger.info("reply_composer outcome=%s reason_code=%s", outcome, reason_code)
    return _assemble(opening, body, closing)
