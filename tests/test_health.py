from fastapi.testclient import TestClient

from app.main import app


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_models_cover_nine_tables():
    from app.core.database import Base
    import app.models  # noqa: F401
    assert len(Base.metadata.tables) == 9
