"""Vendor coverage is intentionally light: vendors.py and customers.py both
delegate to the same party_views.PartyWeb, so test_customers.py already
covers the shared logic (validation, confirm step, duplicates, sync
tokens). These tests exist to prove the vendor wiring itself works end to
end, not to re-test logic that's already proven generic."""

from __future__ import annotations

import httpx

from .conftest import extract_csrf, login

VENDOR_RECORD = {"Id": "200", "SyncToken": "0", "DisplayName": "Acme Supplies", "Active": True, "CurrencyRef": {"value": "USD"}}


def _new_vendor_form_data(csrf: str, external_id: str, **overrides) -> dict:
    data = {
        "csrf_token": csrf,
        "external_id": external_id,
        "display_name": "Acme Supplies",
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


def test_new_vendor_form_requires_login(client):
    r = client.get("/vendors/new", follow_redirects=False)
    assert r.status_code == 303


def test_create_vendor_full_flow_success(connected_client):
    client, transport = connected_client
    transport._handlers.append(["POST", "/vendor", lambda req: httpx.Response(200, json={"Vendor": VENDOR_RECORD}), -1])
    transport._handlers.append(["GET", "/vendor/200", lambda req: httpx.Response(200, json={"Vendor": VENDOR_RECORD}), -1])
    login(client)

    r = client.get("/vendors/new")
    csrf = extract_csrf(r.text)
    data = _new_vendor_form_data(csrf, "vend-1")
    r = client.post("/vendors/new", data=data)
    csrf2 = extract_csrf(r.text)
    data["csrf_token"] = csrf2
    data["confirm"] = "yes"

    r = client.post("/vendors/new", data=data, follow_redirects=False)
    assert r.status_code == 303
    assert "/vendors/200" in r.headers["location"]


def test_vendor_detail_view(connected_client):
    client, transport = connected_client
    transport._handlers.append(["GET", "/vendor/200", lambda req: httpx.Response(200, json={"Vendor": VENDOR_RECORD}), -1])
    login(client)

    r = client.get("/vendors/200")
    assert r.status_code == 200
    assert "Acme Supplies" in r.text
