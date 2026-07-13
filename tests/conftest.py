"""pytest fixtures。

db_engine：乾淨 test DB → `alembic upgrade head`(真 PostgreSQL) → yield engine → drop。
⛔ 不用 create_all()：那會直接從 models 建表 → 永遠一致 → schema drift 測試永遠綠、失去意義。
必須是「alembic 建的 DB」對比「models」，才抓得到漂移。
"""
import os
import subprocess

import pytest
from sqlalchemy import create_engine, text

from app.core.config import get_settings

_TEST_DB = "orderai_drift_test"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALEMBIC = os.path.join(_REPO_ROOT, ".venv", "bin", "alembic")


def _base_prefix() -> str:
    # postgresql+psycopg2://orderai:orderai@localhost:5432/<db> → 去掉 /<db>
    return get_settings().database_url.rsplit("/", 1)[0]


def _admin_engine():
    return create_engine(_base_prefix() + "/postgres", isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="session")
def db_engine():
    test_url = _base_prefix() + "/" + _TEST_DB
    admin = _admin_engine()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB}"))
        c.execute(text(f"CREATE DATABASE {_TEST_DB}"))
    admin.dispose()

    # 真 alembic upgrade head（DATABASE_URL 走 env，env.py 的 get_settings 會讀到）
    env = {**os.environ, "DATABASE_URL": test_url}
    r = subprocess.run(
        [_ALEMBIC, "upgrade", "head"],
        env=env, cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed:\n{r.stdout}\n{r.stderr}")

    eng = create_engine(test_url)
    yield eng
    eng.dispose()

    admin = _admin_engine()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB}"))
    admin.dispose()
