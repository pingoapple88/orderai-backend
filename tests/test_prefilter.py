"""情境二：AI 前置意圖預檢（pre-filter）。"""
from app.services.ai_service import is_order_message
from app.models import SystemSetting


class _FakeDB:
    """最小 stub：模擬 db.get(SystemSetting, key)。"""
    def __init__(self, regex):
        self._regex = regex
    def get(self, model, key):
        if key == "pre_filter_regex":
            return SystemSetting(key=key, value=self._regex)
        return None


REGEX = r"(\+\s*\d+|＋\s*\d+|#下單|要買|預購|下單|訂購|\d+\s*份|\d+\s*個|\d+\s*組)"


def test_order_messages_pass():
    db = _FakeDB(REGEX)
    for msg in ["肉乾+2 魚酥+1", "#下單 雞排一份", "我要買 3 份", "預購蛋糕"]:
        assert is_order_message(db, msg) is True, msg


def test_chitchat_blocked():
    db = _FakeDB(REGEX)
    for msg in ["早安大家", "這款我上次買過真好吃", "謝謝老闆", "（貼圖）", ""]:
        assert is_order_message(db, msg) is False, msg
