"""line_callback 建新 user + store 的實跑測試（Bug 修復回歸）。

原本零覆蓋 → 上線才炸(stores 缺欄位、users 缺 picture_url)。
本測試 mock LINE exchange_code，實際打 callback，斷言 user+store 建立成功、
picture_url 寫入成功。依賴 DB 在 head(含 0002 補欄位)。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.main import app
from app.models import Store, User

_LINE_ID = "Utest_callback_fixture_0002"


def _cleanup(line_id: str) -> None:
    # 明確順序：先刪 user（解除 users.store_id FK），再刪 store。
    db = SessionLocal()
    try:
        store_id = db.execute(
            select(User.store_id).where(User.line_id == line_id)
        ).scalar_one_or_none()
        db.execute(text("DELETE FROM users WHERE line_id = :l"), {"l": line_id})
        if store_id:
            db.execute(text("DELETE FROM stores WHERE id = :s"), {"s": store_id})
        db.commit()
    finally:
        db.close()


def test_line_callback_creates_user_and_store():
    _cleanup(_LINE_ID)  # 前置清理，測試冪等
    fake_profile = SimpleNamespace(
        external_id=_LINE_ID, display_name="測試店", avatar_url="http://x/a.png"
    )
    provider = SimpleNamespace(exchange_code=AsyncMock(return_value=fake_profile))
    try:
        with patch("app.api.v1.auth.get_auth_provider", return_value=provider):
            client = TestClient(app)
            r = client.get("/api/v1/auth/line/callback?code=fakecode", follow_redirects=False)

        # 建單成功 → 302/307 導回前端（若 stores/users 缺欄位會 500）
        assert r.status_code in (302, 307), f"expected redirect, got {r.status_code}: {r.text}"

        db = SessionLocal()
        user = db.execute(select(User).where(User.line_id == _LINE_ID)).scalar_one_or_none()
        assert user is not None, "callback 應建立 user"
        assert user.store_id is not None, "user 應綁定 store"
        assert user.picture_url == "http://x/a.png", "picture_url 應寫入成功（Bug 2）"
        store = db.get(Store, user.store_id)
        assert store is not None and store.market == "tw", "應建立 store"
        db.close()
    finally:
        _cleanup(_LINE_ID)
