from __future__ import annotations

from erp_poc.web.db import _normalize_database_url


def test_bare_postgres_scheme_gets_psycopg_driver():
    assert _normalize_database_url("postgres://u:p@host/db").startswith("postgresql+psycopg://u:p@host/db")


def test_bare_postgresql_scheme_gets_psycopg_driver():
    assert _normalize_database_url("postgresql://u:p@host/db").startswith("postgresql+psycopg://u:p@host/db")


def test_already_explicit_driver_left_unchanged():
    url = "postgresql+psycopg://u:p@host/db"
    assert _normalize_database_url(url) == url


def test_sqlite_url_left_unchanged():
    url = "sqlite:///./.state/web.db"
    assert _normalize_database_url(url) == url
