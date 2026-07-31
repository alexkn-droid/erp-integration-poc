from __future__ import annotations

from .conftest import TEST_PASSWORD, extract_csrf, login


def test_unauthenticated_root_redirects_to_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_unauthenticated_customers_page_redirects_to_login(client):
    r = client.get("/customers", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_login_page_renders_without_auth(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "Shared password" in r.text or "password" in r.text.lower()


def test_wrong_password_rejected(client):
    r = client.get("/login")
    csrf = extract_csrf(r.text)
    r = client.post("/login", data={"password": "not-the-password", "csrf_token": csrf})
    assert r.status_code == 401
    assert "Incorrect password" in r.text


def test_correct_password_logs_in_and_grants_access(client):
    r = login(client)
    assert r.status_code == 303
    assert r.headers["location"] == "/"

    r = client.get("/")
    assert r.status_code == 200


def test_login_with_mismatched_csrf_token_rejected(client):
    client.get("/login")  # sets the pre-auth session cookie
    r = client.post("/login", data={"password": TEST_PASSWORD, "csrf_token": "bogus-token"})
    assert r.status_code == 400


def test_logout_requires_login(client):
    r = client.post("/logout", data={"csrf_token": "whatever"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_logout_clears_session(client):
    login(client)
    r = client.get("/")
    csrf = extract_csrf(r.text)

    r = client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"

    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_logout_with_bad_csrf_token_rejected(client):
    login(client)
    r = client.post("/logout", data={"csrf_token": "bogus"})
    assert r.status_code == 400
