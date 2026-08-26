"""LINE OAuth state cookie 與 callback 的合成回歸測試。

所有案例使用 HTTPS TestClient 與 mock provider；不連線正式 LINE、不使用正式憑證。
授權入口先建立 HttpOnly/Secure/SameSite=Lax 的 state cookie，callback 僅接受
同一個 cookie 與 query state，成功後一次性清除。
"""
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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


def _provider(profile: SimpleNamespace | None = None, error: Exception | None = None):
    def _authorize_url(state: str) -> str:
        return f"https://line.example.invalid/authorize?state={state}"

    exchange_code = AsyncMock(return_value=profile)
    if error is not None:
        exchange_code.side_effect = error
    return SimpleNamespace(get_authorize_url=Mock(side_effect=_authorize_url), exchange_code=exchange_code)


def _start_login(provider) -> tuple[TestClient, str, object]:
    client = TestClient(app, base_url="https://testserver")
    with patch("app.api.v1.auth.get_auth_provider", return_value=provider):
        response = client.get("/api/v1/auth/line/login", follow_redirects=False)

    assert response.status_code == 302
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    assert client.cookies.get("line_oauth_state") == state
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "max-age=600" in set_cookie
    return client, state, response


def _callback(client: TestClient, provider, *, code: str = "fakecode", state: str | None = None):
    query = f"code={code}"
    if state is not None:
        query += f"&state={state}"
    with patch("app.api.v1.auth.get_auth_provider", return_value=provider):
        return client.get(f"/api/v1/auth/line/callback?{query}", follow_redirects=False)


def test_line_callback_valid_state_creates_user_store_and_clears_cookie():
    _cleanup(_LINE_ID)
    fake_profile = SimpleNamespace(external_id=_LINE_ID, display_name="測試店", avatar_url="http://x/a.png")
    provider = _provider(profile=fake_profile)
    try:
        client, state, _ = _start_login(provider)
        response = _callback(client, provider, state=state)

        assert response.status_code in (302, 307), response.text
        assert "line_oauth_state=\"\"" in response.headers["set-cookie"].lower()
        assert "max-age=0" in response.headers["set-cookie"].lower()
        assert client.cookies.get("line_oauth_state") is None

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


def test_line_callback_rejects_missing_state():
    provider = _provider(profile=SimpleNamespace(external_id="Umissing", display_name="測試店", avatar_url=None))
    client, _, _ = _start_login(provider)
    response = _callback(client, provider)

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Invalid state"
    provider.exchange_code.assert_not_awaited()


def test_line_callback_rejects_mismatched_state():
    provider = _provider(profile=SimpleNamespace(external_id="Umismatch", display_name="測試店", avatar_url=None))
    client, _, _ = _start_login(provider)
    response = _callback(client, provider, state="different-state")

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Invalid state"
    provider.exchange_code.assert_not_awaited()


def test_line_callback_rejects_expired_cookie_simulation():
    provider = _provider(profile=SimpleNamespace(external_id="Uexpired", display_name="測試店", avatar_url=None))
    client, state, _ = _start_login(provider)
    client.cookies.clear()  # 模擬瀏覽器在 Max-Age=600 到期後不再送出 cookie。
    response = _callback(client, provider, state=state)

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Invalid state"
    provider.exchange_code.assert_not_awaited()


def test_line_callback_rejects_replayed_state_after_success():
    line_id = "Ureplay_callback_fixture"
    _cleanup(line_id)
    provider = _provider(profile=SimpleNamespace(external_id=line_id, display_name="重放測試店", avatar_url=None))
    try:
        client, state, _ = _start_login(provider)
        first = _callback(client, provider, state=state)
        replay = _callback(client, provider, state=state)

        assert first.status_code in (302, 307)
        assert replay.status_code == 400
        assert replay.json()["error"]["message"] == "Invalid state"
        assert provider.exchange_code.await_count == 1
    finally:
        _cleanup(line_id)


def test_line_callback_provider_error_keeps_state_validation_and_returns_error():
    provider = _provider(error=RuntimeError("synthetic provider failure"))
    client, state, _ = _start_login(provider)
    response = _callback(client, provider, state=state)

    assert response.status_code == 500
    assert "LINE exchange failed" in response.json()["error"]["message"]
    provider.exchange_code.assert_awaited_once_with("fakecode")
