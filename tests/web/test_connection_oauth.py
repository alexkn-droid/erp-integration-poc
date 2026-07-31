from __future__ import annotations

import httpx

from erp_poc.qbo_auth import TokenSet
from erp_poc.web.stores import DbTokenStore

from .conftest import default_handlers, login


def test_connection_start_requires_login(client):
    r = client.get("/connection/start", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_connection_start_redirects_to_intuit_with_state_cookie(client):
    login(client)
    r = client.get("/connection/start", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("https://appcenter.intuit.com/connect/oauth2")
    assert "state=" in r.headers["location"]
    assert any(c for c in r.cookies if "oauth_state" in c)


def test_connection_callback_rejects_missing_state(client):
    r = client.get("/connection/callback", params={"code": "abc", "realmId": "123"})
    assert r.status_code == 400
    assert "could not be verified" in r.text.lower()


def test_connection_callback_rejects_mismatched_state(client):
    login(client)
    start = client.get("/connection/start", follow_redirects=False)
    assert start.status_code == 303

    r = client.get("/connection/callback", params={"code": "abc", "realmId": "123", "state": "not-the-real-state"})
    assert r.status_code == 400


def test_connection_callback_success_exchanges_code_and_stores_connection(client, monkeypatch):
    login(client)
    start = client.get("/connection/start", follow_redirects=False)
    real_state = start.headers["location"].split("state=")[1].split("&")[0]

    def fake_exchange(settings, *, authorization_code: str) -> TokenSet:
        assert authorization_code == "real-auth-code"
        return TokenSet(access_token="new-access-token", refresh_token="new-refresh-token", expires_at_epoch=9999999999.0)

    monkeypatch.setattr("erp_poc.qbo_auth.exchange_code_for_tokens", fake_exchange)

    def company_info(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"CompanyInfo": {"CompanyName": "Newly Connected Co", "Id": "1"}})

    client.app.state.qbo_transport = httpx.MockTransport(company_info)

    r = client.get(
        "/connection/callback",
        params={"code": "real-auth-code", "realmId": "555555", "state": real_state},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/connection")

    r = client.get("/connection")
    assert "Connected" in r.text
    assert "Newly Connected Co" in r.text
    assert "555555" in r.text


def test_disconnect_requires_login_and_csrf(client):
    r = client.post("/connection/disconnect", data={"csrf_token": "x"}, follow_redirects=False)
    assert r.status_code == 303  # not logged in -> redirected to login, not a 400

    login(client)
    r = client.post("/connection/disconnect", data={"csrf_token": "bogus"})
    assert r.status_code == 400


def test_disconnect_clears_connection(connected_client):
    client, _ = connected_client
    login(client)
    r = client.get("/connection")
    from .conftest import extract_csrf

    csrf = extract_csrf(r.text)

    r = client.post("/connection/disconnect", data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 303

    r = client.get("/connection")
    assert "Not connected" in r.text


def test_connection_health_check_surfaces_expired_auth_clearly(connected_client):
    client, transport = connected_client
    # Replace the default companyinfo handler with one that reports an expired token.
    transport._handlers.insert(0, ["GET", "/companyinfo/", lambda req: httpx.Response(401, json={}), -1])
    login(client)

    r = client.get("/connection")
    assert r.status_code == 200
    assert "Failing" in r.text
    # The connection page itself catches the ERPError inline (not the app-level
    # handler) so it can show status alongside the rest of the page.


def test_reading_a_customer_with_expired_token_shows_plain_language_message(connected_client):
    client, transport = connected_client
    transport._handlers.insert(0, ["GET", "/customer/100", lambda req: httpx.Response(401, json={}), -1])
    login(client)

    r = client.get("/customers/100")
    assert r.status_code == 502
    assert "reconnect" in r.text.lower()
    assert "traceback" not in r.text.lower()


def test_token_store_persists_across_sessions(web_settings, app_with_transport):
    app, _ = app_with_transport(web_settings, default_handlers())
    db1 = app.state.session_factory()
    DbTokenStore(db1).save_new_connection(
        realm_id="42", company_name="Persist Co",
        tokens=TokenSet(access_token="tok-a", refresh_token="ref-a", expires_at_epoch=1234.0),
    )
    db1.close()

    db2 = app.state.session_factory()
    loaded = DbTokenStore(db2).load()
    assert loaded is not None
    assert loaded.access_token == "tok-a"
    assert loaded.refresh_token == "ref-a"
    db2.close()


def test_reconnect_replaces_previous_connection_not_adds_second(web_settings, app_with_transport):
    from sqlalchemy import select

    from erp_poc.web.models_db import QboConnection

    app, _ = app_with_transport(web_settings, default_handlers())
    db = app.state.session_factory()
    store = DbTokenStore(db)
    store.save_new_connection(realm_id="1", company_name="First", tokens=TokenSet("a", "b", 1.0))
    store.save_new_connection(realm_id="2", company_name="Second", tokens=TokenSet("c", "d", 2.0))

    rows = db.execute(select(QboConnection)).scalars().all()
    assert len(rows) == 1
    assert rows[0].realm_id == "2"
    db.close()
