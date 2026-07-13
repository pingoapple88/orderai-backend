"""確保 SQLAlchemy models 與實際 DB schema 完全一致。

存在理由：2026-07-13 squash migration 時 schema.sql 的 stores 表漏了 0004 的欄位，
models 卻有 → 登入 callback 上線後 500。原測試只數表數量(14)沒抓到。從此逐欄比對。

db_engine 是「alembic upgrade head 建的真 PostgreSQL」對比「models」，才抓得到漂移。
"""
from sqlalchemy import inspect

from app.models import Base


def test_models_match_db_columns(db_engine):
    """每個 model 的每個欄位，都必須存在於實際 DB（alembic 建的）。"""
    inspector = inspect(db_engine)
    db_tables = set(inspector.get_table_names())

    errors = []
    for table_name, table in Base.metadata.tables.items():
        if table_name not in db_tables:
            errors.append(f"表不存在於 DB: {table_name}")
            continue

        db_cols = {c["name"] for c in inspector.get_columns(table_name)}
        model_cols = {c.name for c in table.columns}

        missing_in_db = model_cols - db_cols
        if missing_in_db:
            errors.append(f"{table_name}: model 有但 DB 沒有 → {sorted(missing_in_db)}")

        extra_in_db = db_cols - model_cols
        if extra_in_db:
            # 反向只當警告：DB 可以有 model 不用的欄位（舊欄待清）
            print(f"[warn] {table_name}: DB 有但 model 沒有 → {sorted(extra_in_db)}")

    assert not errors, "Schema 漂移:\n" + "\n".join(errors)
