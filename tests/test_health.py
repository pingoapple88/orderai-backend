from fastapi.testclient import TestClient
from app.main import app


def test_health():
    assert TestClient(app).get("/health").json()["status"] == "ok"


def test_models_cover_eleven_tables():
    from app.core.database import Base
    import app.models  # noqa
    assert len(Base.metadata.tables) == 11
    assert "system_settings" in Base.metadata.tables
    assert "tenants" in Base.metadata.tables
