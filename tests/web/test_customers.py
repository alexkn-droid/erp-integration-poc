from __future__ import annotations

import httpx

from .conftest import default_handlers, extract_csrf, login

CUSTOMER_RECORD = {"Id": "100", "SyncToken": "0", "DisplayName": "Acme Corp", "Active": True, "CurrencyRef": {"value": "USD"}}
CUSTOMER_RECORD_V1 = {**CUSTOMER_RECORD, "SyncToken": "1", "CompanyName": "Acme Corp (Updated)"}


def _new_customer_form_data(csrf: str, external_id: str, **overrides) -> dict:
    data = {
        "csrf_token": csrf,
        "external_id": external_id,
        "display_name": "Acme Corp",
        "company_name": "",
        "email": "",
        "phone": "",
        "address_line1": "",
        "address_line2": "",
        "city": "",
        "state": "",
        "postal_code": "",
        "country": "",
        "currency": "USD",
        "is_active": "on",
    }
    data.update(overrides)
    return data


def test_customers_page_without_connection_prompts_to_connect(client):
    login(client)
    r = client.get("/customers")
    assert r.status_code == 200
    assert "not connected" in r.text.lower()


def test_new_customer_form_requires_login(client):
    r = client.get("/customers/new", follow_redirects=False)
    assert r.status_code == 303


def test_new_customer_form_prefills_generated_external_id(client):
    login(client)
    r = client.get("/customers/new")
    assert r.status_code == 200
    assert 'name="external_id" value="' in r.text


def test_create_customer_validation_error_blank_display_name(connected_client):
    client, _ = connected_client
    login(client)
    r = client.get("/customers/new")
    csrf = extract_csrf(r.text)

    data = _new_customer_form_data(csrf, "ext-1", display_name="")
    r = client.post("/customers/new", data=data)
    assert r.status_code == 400
    assert "display_name" in r.text.lower() or "please fix" in r.text.lower()


def test_create_customer_requires_confirm_step_before_writing(connected_client):
    client, transport = connected_client
    login(client)
    r = client.get("/customers/new")
    csrf = extract_csrf(r.text)

    data = _new_customer_form_data(csrf, "ext-1")
    r = client.post("/customers/new", data=data)
    assert r.status_code == 200
    assert "Review before sending to QuickBooks" in r.text
    # No write should have happened yet.
    assert all(req.method != "POST" for req in transport.requests)


def test_create_customer_full_flow_success(connected_client):
    client, transport = connected_client
    transport._handlers.append(["POST", "/customer", lambda req: httpx.Response(200, json={"Customer": CUSTOMER_RECORD}), -1])
    transport._handlers.append(["GET", "/customer/100", lambda req: httpx.Response(200, json={"Customer": CUSTOMER_RECORD}), -1])
    login(client)

    r = client.get("/customers/new")
    csrf = extract_csrf(r.text)
    data = _new_customer_form_data(csrf, "ext-1")
    r = client.post("/customers/new", data=data)
    csrf2 = extract_csrf(r.text)

    data["csrf_token"] = csrf2
    data["confirm"] = "yes"
    r = client.post("/customers/new", data=data, follow_redirects=False)
    assert r.status_code == 303
    assert "/customers/100" in r.headers["location"]
    assert "created" in r.headers["location"].lower()


def test_create_customer_duplicate_detected_without_second_write(connected_client):
    client, transport = connected_client

    def matched_query(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"QueryResponse": {"Customer": [CUSTOMER_RECORD]}})

    # Override the default empty-query handler with one that reports a match.
    transport._handlers.insert(0, ["GET", "/query", matched_query, -1])

    login(client)
    r = client.get("/customers/new")
    csrf = extract_csrf(r.text)
    data = _new_customer_form_data(csrf, "ext-1")
    r = client.post("/customers/new", data=data)
    csrf2 = extract_csrf(r.text)
    data["csrf_token"] = csrf2
    data["confirm"] = "yes"

    r = client.post("/customers/new", data=data, follow_redirects=False)
    assert r.status_code == 303
    assert "already" in r.headers["location"]
    assert all(req.method != "POST" for req in transport.requests)


def test_search_customers(connected_client):
    client, transport = connected_client

    def search(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"QueryResponse": {"Customer": [CUSTOMER_RECORD]}})

    transport._handlers.insert(0, ["GET", "/query", search, -1])

    login(client)
    r = client.get("/customers", params={"q": "Acme"})
    assert r.status_code == 200
    assert "Acme Corp" in r.text


def test_view_customer_detail_shows_qbo_id_and_sync_token(connected_client):
    client, transport = connected_client
    transport._handlers.append(["GET", "/customer/100", lambda req: httpx.Response(200, json={"Customer": CUSTOMER_RECORD}), -1])

    login(client)
    r = client.get("/customers/100")
    assert r.status_code == 200
    assert "100" in r.text
    assert "Sync token" in r.text


def test_update_customer_uses_current_sync_token(connected_client):
    client, transport = connected_client
    call_count = {"reads": 0}

    def read(request: httpx.Request) -> httpx.Response:
        call_count["reads"] += 1
        # The first read is edit_form()'s prefetch to prime the form (SyncToken "0",
        # now stale). Every read after that simulates the record having since
        # changed server-side, so the freshest SyncToken by the time update()
        # re-reads immediately before writing is "5" — proving that value, not
        # the stale one the form was loaded with, is what actually gets sent.
        token = "0" if call_count["reads"] == 1 else "5"
        return httpx.Response(200, json={"Customer": {**CUSTOMER_RECORD, "SyncToken": token}})

    def update(request: httpx.Request) -> httpx.Response:
        body = request.content.decode().replace(" ", "")
        assert '"SyncToken":"5"' in body, body
        return httpx.Response(200, json={"Customer": CUSTOMER_RECORD_V1})

    transport._handlers.append(["GET", "/customer/100", read, -1])
    transport._handlers.append(["POST", "/customer", update, -1])

    login(client)
    r = client.get("/customers/100/edit")
    csrf = extract_csrf(r.text)
    data = _new_customer_form_data(csrf, "100", company_name="Acme Corp (Updated)")
    r = client.post("/customers/100/edit", data=data)
    csrf2 = extract_csrf(r.text)
    data["csrf_token"] = csrf2
    data["confirm"] = "yes"

    r = client.post("/customers/100/edit", data=data, follow_redirects=False)
    assert r.status_code == 303
    assert "updated" in r.headers["location"].lower()


def test_sandbox_only_write_enforcement_blocks_non_sandbox_create(web_settings, app_with_transport):
    web_settings.qbo_environment = "production"
    app, transport = app_with_transport(web_settings, default_handlers())
    from fastapi.testclient import TestClient

    client = TestClient(app)
    login(client)

    r = client.get("/customers/new")
    csrf = extract_csrf(r.text)
    data = _new_customer_form_data(csrf, "ext-1")
    data["confirm"] = "yes"
    r = client.post("/customers/new", data=data)

    assert r.status_code == 403
    assert all(req.method != "POST" for req in transport.requests)
