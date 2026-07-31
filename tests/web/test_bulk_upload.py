from __future__ import annotations

import httpx

from .conftest import extract_csrf, login


def test_bulk_upload_form_requires_login(client):
    r = client.get("/bulk-upload", follow_redirects=False)
    assert r.status_code == 303


def test_bulk_upload_rejects_non_csv_extension(connected_client):
    client, _ = connected_client
    login(client)
    r = client.get("/bulk-upload")
    csrf = extract_csrf(r.text)

    files = {"file": ("customers.xlsx", b"not really a csv", "application/vnd.ms-excel")}
    r = client.post("/bulk-upload", data={"entity_type": "customer", "csrf_token": csrf}, files=files)
    assert r.status_code == 200
    assert ".csv" in r.text


def test_bulk_upload_rejects_zip_based_spreadsheet_disguised_as_csv(connected_client):
    client, _ = connected_client
    login(client)
    r = client.get("/bulk-upload")
    csrf = extract_csrf(r.text)

    # Real .xlsx files are zip archives; a zip signature with a .csv extension
    # should still be rejected rather than parsed as text.
    files = {"file": ("customers.csv", b"PK\x03\x04fake-zip-content", "text/csv")}
    r = client.post("/bulk-upload", data={"entity_type": "customer", "csrf_token": csrf}, files=files)
    assert r.status_code == 200
    assert "spreadsheet" in r.text.lower()


def test_bulk_upload_rejects_missing_required_column(connected_client):
    client, _ = connected_client
    login(client)
    r = client.get("/bulk-upload")
    csrf = extract_csrf(r.text)

    csv_content = b"company_name,email\nAcme,a@example.com\n"
    files = {"file": ("customers.csv", csv_content, "text/csv")}
    r = client.post("/bulk-upload", data={"entity_type": "customer", "csrf_token": csrf}, files=files)
    assert r.status_code == 200
    assert "display_name" in r.text.lower()


def test_bulk_upload_preview_shows_row_level_validation_errors(connected_client):
    client, _ = connected_client
    login(client)
    r = client.get("/bulk-upload")
    csrf = extract_csrf(r.text)

    csv_content = b"display_name,email\nGood Row,a@example.com\n,bad@example.com\n"
    files = {"file": ("customers.csv", csv_content, "text/csv")}
    r = client.post("/bulk-upload", data={"entity_type": "customer", "csrf_token": csrf}, files=files, follow_redirects=False)
    assert r.status_code == 303
    preview_url = r.headers["location"]

    r = client.get(preview_url)
    assert r.status_code == 200
    assert "Valid" in r.text
    assert "Invalid" in r.text


def test_bulk_upload_mixed_success_continues_past_failed_row(connected_client):
    client, transport = connected_client

    call_count = {"n": 0}

    def create(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        record = {"Id": str(100 + call_count["n"]), "SyncToken": "0", "DisplayName": f"Row {call_count['n']}", "Active": True}
        return httpx.Response(200, json={"Customer": record})

    def read(request: httpx.Request) -> httpx.Response:
        entity_id = str(request.url).rsplit("/", 1)[-1]
        return httpx.Response(200, json={"Customer": {"Id": entity_id, "SyncToken": "0", "DisplayName": "x", "Active": True}})

    transport._handlers.append(["POST", "/customer", create, -1])
    transport._handlers.append(["GET", "/customer/", read, -1])

    login(client)
    r = client.get("/bulk-upload")
    csrf = extract_csrf(r.text)

    csv_content = b"display_name,email\nRow One,a@example.com\n,bad@example.com\nRow Two,b@example.com\n"
    files = {"file": ("customers.csv", csv_content, "text/csv")}
    r = client.post("/bulk-upload", data={"entity_type": "customer", "csrf_token": csrf}, files=files, follow_redirects=False)
    preview_url = r.headers["location"]

    r = client.get(preview_url)
    csrf = extract_csrf(r.text)
    job_id = preview_url.split("/")[2]

    r = client.post(f"/bulk-upload/{job_id}/confirm", data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 303

    r = client.get(f"/bulk-upload/{job_id}/results")
    assert r.status_code == 200
    # Two valid rows created despite one invalid row in between.
    assert call_count["n"] == 2
    assert "failed" in r.text.lower()
    assert "created" in r.text.lower()

    r = client.get(f"/bulk-upload/{job_id}/download")
    assert r.status_code == 200
    assert "Row One" in r.text
    assert "Row Two" in r.text


def test_bulk_upload_rejects_more_rows_than_the_configured_limit(web_settings, app_with_transport):
    from fastapi.testclient import TestClient

    web_settings.max_upload_rows = 2
    app, _ = app_with_transport(web_settings, [])
    client = TestClient(app)
    login(client)

    r = client.get("/bulk-upload")
    csrf = extract_csrf(r.text)
    csv_content = b"display_name\nRow One\nRow Two\nRow Three\n"  # 3 rows > limit of 2
    files = {"file": ("customers.csv", csv_content, "text/csv")}
    r = client.post("/bulk-upload", data={"entity_type": "customer", "csrf_token": csrf}, files=files)
    assert r.status_code == 200
    assert "more than 2" in r.text


def test_bulk_upload_sandbox_only_enforcement(web_settings, app_with_transport):
    from .conftest import default_handlers

    web_settings.qbo_environment = "production"
    app, transport = app_with_transport(web_settings, default_handlers())
    from fastapi.testclient import TestClient

    client = TestClient(app)
    login(client)

    r = client.get("/bulk-upload")
    csrf = extract_csrf(r.text)
    csv_content = b"display_name\nRow One\n"
    files = {"file": ("customers.csv", csv_content, "text/csv")}
    r = client.post("/bulk-upload", data={"entity_type": "customer", "csrf_token": csrf}, files=files, follow_redirects=False)
    preview_url = r.headers["location"]
    r = client.get(preview_url)
    csrf = extract_csrf(r.text)
    job_id = preview_url.split("/")[2]

    r = client.post(f"/bulk-upload/{job_id}/confirm", data={"csrf_token": csrf})
    assert r.status_code == 403
    assert all(req.method != "POST" for req in transport.requests)
