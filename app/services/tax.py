"""計稅（情境三：日本一筆訂單只對總額做一次四捨五入）。"""
from decimal import ROUND_HALF_UP, Decimal

# 各市場稅率（之後可移入 system_settings）
_TAX_RATE = {
    "jp": Decimal("0.10"),   # 日本消費稅 10%
    "tw": Decimal("0.05"),
    "th": Decimal("0.07"),
    "us": Decimal("0.00"),   # 由州別決定，Phase 1 預設 0
}


def compute_tax(total_amount: int, market: str) -> int:
    """對「訂單總額」整體計稅並四捨五入一次，回傳整數分位稅額。

    關鍵（日本 Invoice 制度）：絕不逐項計稅後加總，避免尾數誤差。
    total_amount 與回傳值皆為整數分位（最小幣別單位）。
    """
    rate = _TAX_RATE.get(market.lower(), Decimal("0"))
    tax = (Decimal(total_amount) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(tax)
