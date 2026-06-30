"""情境三：日本一次性計稅（對總額四捨五入一次，杜絕逐項尾數誤差）。"""
from app.services.tax import compute_tax


def test_jp_single_rounding_vs_per_item():
    # 3 件，每件 333（整數分位）。逐項計稅: round(33.3)=33 ×3 = 99。
    # 正確（對總額一次）: 999 ×0.10 = 99.9 → round = 100。
    assert compute_tax(999, "jp") == 100


def test_jp_basic_rate():
    assert compute_tax(20000, "jp") == 2000  # 10%


def test_tw_rate():
    assert compute_tax(10000, "tw") == 500   # 5%


def test_unknown_market_zero_tax():
    assert compute_tax(10000, "xx") == 0
