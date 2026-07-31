from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import httpx
import pytest
from fastapi.testclient import TestClient

from erp_poc.qbo_auth import TokenSet
from erp_poc.web.app import create_app
from erp_poc.web.config import WebSettings
from erp_poc.web.db import Base, make_engine, make_session_factory
from erp_poc.web.security import generate_app_secret_key, hash_password
from erp_poc.web.stores import DbTokenStore

TEST_PASSWORD = "test-password-123"
TEST_REALM_ID = "9999999999"


class ScriptedTransport(httpx.BaseTransport):
    """Same pattern as tests/test_service_mocked.py's ScriptedTransport:
    routes requests to handlers in order, each usable a limited (or
    unlimited, via -1) number of times. No network call ever leaves the
    process in these tests."""

    def __init__(self, handlers: list[tuple[str, str, "callable", int]]) -> None:
        self._handlers = [list(h) for h in handlers]
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for handler in self._handlers:
            method, path_substr, factory, remaining = handler
            if remaining == 0:
                continue
            if request.method == method and path_substr in str(request.url):
                handler[3] = remaining - 1 if remaining > 0 else remaining
                return factory(request)
        raise AssertionError(f"No mocked handler matched {request.method} {request.url}")


def company_info_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"CompanyInfo": {"CompanyName": "Test Sandbox Co", "Id": "1"}})


def empty_query_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"QueryResponse": {}})


def default_handlers() -> list[tuple[str, str, "callable", int]]:
    return [
        ("GET", "/companyinfo/", company_info_handler, -1),
        ("GET", "/query", empty_query_handler, -1),
    ]


@pytest.fixture
def web_settings() -> WebSettings:
    return WebSettings(
        qbo_client_id="test-client-id",
        qbo_client_secret="test-client-secret",
        qbo_environment="sandbox",
        qbo_redirect_uri="http://testserver/connection/callback",
        app_secret_key=generate_app_secret_key(),
        shared_password_hash=hash_password(TEST_PASSWORD),
        database_url="sqlite:///:memory:",
    )


def _build_app(web_settings: WebSettings, transport: httpx.BaseTransport | None):
    engine = make_engine(web_settings.database_url)
    Base.metadata.create_all(engine)
    return create_app(web_settings, engine=engine, qbo_transport=transport)


@pytest.fixture
def app_with_transport():
    """Factory fixture: app_with_transport(handlers) -> (app, transport)."""

    def _make(web_settings: WebSettings, handlers: list | None = None):
        transport = ScriptedTransport(handlers) if handlers is not None else None
        app = _build_app(web_settings, transport)
        return app, transport

    return _make


@pytest.fixture
def client(web_settings, app_with_transport) -> TestClient:
    app, _ = app_with_transport(web_settings, None)
    return TestClient(app)


@pytest.fixture
def connected_client(web_settings, app_with_transport):
    """A logged-out TestClient whose app already has a seeded QBO connection
    and a default (companyinfo + empty query) mocked transport. Returns
    (client, transport) so tests can extend `transport._handlers` for
    create/read/update endpoints they specifically need."""
    app, transport = app_with_transport(web_settings, default_handlers())
    db = app.state.session_factory()
    DbTokenStore(db).save_new_connection(
        realm_id=TEST_REALM_ID,
        company_name="Test Sandbox Co",
        tokens=TokenSet(access_token="fake-access-token", refresh_token="fake-refresh-token", expires_at_epoch=time.time() + 3600),
    )
    db.close()
    return TestClient(app), transport


def extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, "csrf_token not found in rendered page"
    return m.group(1)


def login(client: TestClient, password: str = TEST_PASSWORD):
    r = client.get("/login")
    csrf = extract_csrf(r.text)
    return client.post("/login", data={"password": password, "csrf_token": csrf}, follow_redirects=False)
