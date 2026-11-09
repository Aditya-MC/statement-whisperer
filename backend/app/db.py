"""Database engine and session management.

SQLite is the default; any SQLAlchemy URL (e.g. Postgres) works via DATABASE_URL.
"""

from __future__ import annotations

import ssl
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sqlalchemy import Engine, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base with a stable constraint naming convention (needed for Alembic)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_SSL_PARAMS = ("sslmode", "channel_binding", "sslrootcert")


def normalize_postgres_url(url: str) -> tuple[str, bool]:
    """Turn a provider's Postgres URL (e.g. Neon's `postgresql://...?sslmode=require`) into a
    pg8000 SQLAlchemy URL. Returns (url, use_tls).

    pg8000 is pure Python (no compiled extension for Smart App Control to block), but it
    doesn't understand libpq's `sslmode` query option, so TLS is passed as an SSL context.
    TLS is on unless the host is local or sslmode is explicitly disabled.
    """
    parts = urlsplit(url)
    scheme = "postgresql+pg8000"
    query = parse_qs(parts.query)
    sslmode = (query.get("sslmode") or [""])[0]
    clean_query = urlencode({k: v for k, v in query.items() if k not in _SSL_PARAMS}, doseq=True)
    local = (parts.hostname or "") in ("localhost", "127.0.0.1", "::1")
    use_tls = sslmode not in ("disable", "allow") and not (local and not sslmode)
    return urlunsplit((scheme, parts.netloc, parts.path, clean_query, parts.fragment)), use_tls


def make_engine(url: str) -> Engine:
    """Create an engine.

    * SQLite: foreign keys on; in-memory databases share one connection.
    * Postgres (`postgres://`, `postgresql://`, `postgresql+pg8000://`): the pg8000 driver,
      TLS for remote hosts, and connections checked before use. Neon's free databases
      suspend when idle and drop connections.

    Bound parameter values are hidden from SQL logs and error messages.
    """
    # hide_parameters: bound values (narrations, amounts) never appear in SQL logs or in
    # exception messages, even if someone turns on DEBUG logging.
    kwargs: dict[str, Any] = {"hide_parameters": True}
    if url.startswith(("postgres://", "postgresql://", "postgresql+pg8000://")):
        url, use_tls = normalize_postgres_url(url)
        if use_tls:
            kwargs["connect_args"] = {"ssl_context": ssl.create_default_context()}
        kwargs.update(pool_pre_ping=True, pool_recycle=300, pool_size=5, max_overflow=5)
    elif url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url in ("sqlite://", "sqlite+pysqlite://"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(url: str) -> Engine:
    global _engine, _SessionLocal
    _engine = make_engine(url)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session bound to the configured engine."""
    if _SessionLocal is None:
        from app.config import get_settings

        init_engine(get_settings().database_url)
    assert _SessionLocal is not None
    with _SessionLocal() as session:
        yield session
