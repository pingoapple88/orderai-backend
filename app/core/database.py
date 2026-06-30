"""SQLAlchemy engine / session / Base（律五依賴此處解耦）。"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# engine 為惰性連線：import 時不會連 DB，第一次查詢才連。
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """所有 ORM 模型的宣告基底。"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency：每請求一個 session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
