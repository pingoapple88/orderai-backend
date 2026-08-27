"""訂單解析正規化工具。

本模組只處理不可信解析資料的安全轉換；任何無法證實的值維持 None，
交由風險守衛轉為 needs_review，絕不補猜數量或金額。
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class QuantityNormalization:
    value: Optional[int]
    reason_code: Optional[str] = None


def clean_product_name(value: Any) -> str:
    """保留顯示字形，但統一 Unicode 與首尾空白。"""
    if not isinstance(value, str):
        return ""
    return unicodedata.normalize("NFKC", value).strip()


def normalize_product_key(value: Any) -> str:
    """型錄與評測共用的比對 key：NFKC、移除空白、casefold。"""
    return "".join(clean_product_name(value).split()).casefold()


def normalize_quantity(value: Any, *, max_quantity: Optional[int] = None) -> QuantityNormalization:
    """只接受正整數或正整數字串，不接受 bool、float、0、負數或小數。"""
    if isinstance(value, bool):
        return QuantityNormalization(None, "quantity_not_integer")
    if isinstance(value, int):
        quantity = value
    elif isinstance(value, str):
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not re.fullmatch(r"[0-9]+", normalized):
            return QuantityNormalization(None, "quantity_not_integer")
        quantity = int(normalized)
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return QuantityNormalization(None, "quantity_not_integer")
        return QuantityNormalization(None, "quantity_float_not_allowed")
    else:
        return QuantityNormalization(None, "quantity_missing")

    if quantity < 1:
        return QuantityNormalization(None, "quantity_not_positive")
    if max_quantity is not None and quantity > max_quantity:
        return QuantityNormalization(None, "quantity_exceeds_limit")
    return QuantityNormalization(quantity)
