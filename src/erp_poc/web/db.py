"""SQLAlchemy engine/session setup.

`get_db()` is a FastAPI dependency; each request gets its own session,
closed when the request finishes. Tests override this dependency to point
at a temporary SQLite database instead (see tests/web/conftest.py).
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str):
    if database_url.startswith("sqlite"):
        # check_same_thread=False: FastAPI runs sync route handlers in a
        # worker thread pool, so the connection may be used from a
        # different thread than it was created on. StaticPool for
        # ':memory:' specifically: an in-memory SQLite DB is scoped to a
        # single connection, so every session must reuse that same
        # connection or it sees an empty database (used by tests).
        kwargs = {"poolclass": StaticPool} if ":memory:" in database_url else {}
        return create_engine(database_url, connect_args={"check_same_thread": False}, pool_pre_ping=True, **kwargs)
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
