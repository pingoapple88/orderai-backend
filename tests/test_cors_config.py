"""CORS allowed_origins env 化測試（chore/cors-env-config）。

驗證：沒設 ENV 時用預設（現況不變）；設了 ALLOWED_ORIGINS 時用 env、逗號分隔可多個。
"""
from app.core.config import Settings

_DEFAULT = "https://app.orderai.merchcore.ai"


def test_default_when_env_unset():
    """未設 ALLOWED_ORIGINS → 用預設，行為與改動前一致。"""
    s = Settings(_env_file=None)
    assert s.allowed_origins_list == [_DEFAULT]


def test_env_single_origin(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://foo.up.railway.app")
    s = Settings(_env_file=None)
    assert s.allowed_origins_list == ["https://foo.up.railway.app"]


def test_env_multiple_origins(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "https://foo.up.railway.app, https://app.orderai.merchcore.ai",
    )
    s = Settings(_env_file=None)
    # 逗號分隔 → 多個；去空白
    assert s.allowed_origins_list == [
        "https://foo.up.railway.app",
        "https://app.orderai.merchcore.ai",
    ]


def test_env_filters_blank_entries(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.com,, ,https://b.com")
    s = Settings(_env_file=None)
    assert s.allowed_origins_list == ["https://a.com", "https://b.com"]
