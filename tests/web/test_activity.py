from __future__ import annotations

import httpx

from .conftest import extract_csrf, login

CUSTOMER_RECORD = {"Id": "100", "SyncToken": "0", "DisplayName": "Acme Corp", "Active": True, "CurrencyRef": {"value": "USD"}}


def test_activity_page_requires_login(client):
    r = client.get("/activity", follow_redirects=False)
    assert r.status_code == 303


def test_activity_page_empty_by_default(connected_client):
    client, _ = connected_client
    login(client)
    r = client.get("/activity")
    assert r.status_code == 200
    assert "No activity yet" in r.text


def test_creating_a_customer_records_an_activity_entry(connected_client):
    client, transport = connected_client
    transport._handlers.append(["POST", "/customer", lambda req: httpx.Response(200, json={"Customer": CUSTOMER_RECORD}), -1])
    transport._handlers.append(["GET", "/customer/100", lambda req: httpx.Response(200, json={"Customer": CUSTOMER_RECORD}), -1])
    login(client)

    r = client.get("/customers/new")
    csrf = extract_csrf(r.text)
    data = {
        "csrf_token": csrf, "external_id": "ext-1", "display_name": "Acme Corp", "company_name": "",
        "email": "", "phone": "", "address_line1": "", "address_line2": "", "city": "", "state": "",
        "postal_code": "", "country": "", "currency": "USD", "is_active": "on",
    }
    r = client.post("/customers/new", data=data)
    csrf2 = extract_csrf(r.text)
    data["csrf_token"] = csrf2
    data["confirm"] = "yes"
    client.post("/customers/new", data=data)

    r = client.get("/activity")
    assert r.status_code == 200
    assert "sync_customer" in r.text
    assert "ext-1" in r.text
    assert "100" in r.text

    # Never expose tokens or secrets in the activity view.
    assert "fake-access-token" not in r.text
    assert "fake-refresh-token" not in r.text
