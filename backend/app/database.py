from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

settings.db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_columns(conn, table: str) -> set[str]:  # noqa: ANN001
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _ensure_columns() -> None:
    """轻量迁移：为已存在的表补充新增列（SQLite 的 ADD COLUMN）。"""
    migrations: dict[str, dict[str, str]] = {
        "sessions": {
            "settings_token": "TEXT",
            "settings_cookies": "TEXT",
            "mobile_token": "TEXT",
            "mobile_refresh_token": "TEXT",
        },
    }
    with engine.begin() as conn:
        for table, columns in migrations.items():
            existing = _sqlite_columns(conn, table)
            if not existing:
                continue
            for name, ddl_type in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}")


def _migrate_legacy_tokens() -> None:
    """把旧的单一 access_token 迁移到新的分类型字段。

    旧版本用同一个字段混存两套令牌。判定依据（按可靠性排序）：
    1) token_type == 'settings' → 别名会话；
    2) 该记录带有 cookies → 别名会话（只有 CATS 需要 Cookie）；
    3) 其余视为取件（移动 API）会话。
    """
    from .models import SessionToken

    with SessionLocal() as db:
        rows = db.query(SessionToken).all()
        changed = False
        for row in rows:
            legacy = row.access_token
            if not legacy:
                continue
            looks_like_settings = row.token_type == "settings" or bool(row.cookies)
            if looks_like_settings and not row.settings_token:
                row.settings_token = legacy
                row.settings_cookies = row.cookies
                row.access_token = None
                changed = True
            elif not looks_like_settings and not row.mobile_token:
                row.mobile_token = legacy
                row.access_token = None
                changed = True
        if changed:
            db.commit()


def init_db() -> None:
    from . import models  # noqa: F401  确保模型已注册
    from .database import engine as _engine

    models.Base.metadata.create_all(bind=_engine)
    _ensure_columns()
    _migrate_legacy_tokens()
