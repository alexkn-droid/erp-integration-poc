"""End-to-end service tests against a mocked QBO API (httpx.MockTransport).

No network call ever leaves the process in this file. This is the
"mocked API tests" deliverable — it proves the orchestration logic
(idempotency, human-approval gate, retry, read-back) is correct
independent of whether a live sandbox is reachable.
"""

from __future__ import annotations

import time

import httpx
import pytest

from erp_poc.audit import AuditTrail
from erp_poc.canonical import CanonicalCustomer
from erp_poc.errors import ERPAuthError
from erp_poc.idempotency import IdempotencyStore
from erp_poc.qbo_auth import TokenSet, TokenStore
from erp_poc.qbo_client import QBOClient
from erp_poc.service import CustomerSyncService

QBO_CUSTOMER_RECORD = {
    "Id": "100",
    "SyncToken": "0",
    "DisplayName": "Acme Corp",
    "Active": True,
    "CurrencyRef": {"value": "USD"},
}


class ScriptedTransport(httpx.BaseTransport):
    """Routes requests to a list of (matcher, response_factory) pairs in order.

    Each handler is consumed at most `times` calls; falls through to the
    next handler once exhausted. Records every request for assertions.
    """

    def __init__(self, handlers: list[tuple[str, str, callable, int]]) -> None:
        self._handlers = [list(h) for h in handlers]  # [method, path_substr, factory, remaining]
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
        raise AssertionError(f"No handler matched {request.method} {request.url}")


def _seed_valid_token(settings) -> TokenStore:
    store = TokenStore(settings.qbo_token_store_path)
    store.save(TokenSet(access_token="fake-access-token", refresh_token="fake-refresh-token", expires_at_epoch=time.time() + 3600))
    return store


def _build_service(settings, transport) -> tuple[CustomerSyncService, QBOClient]:
    token_store = _seed_valid_token(settings)
    client = QBOClient(settings, token_store, transport=transport)
    idempotency = IdempotencyStore(settings.idempotency_store_path)
    audit = AuditTrail(settings.audit_log_path)
    return CustomerSyncService(settings, client, idempotency, audit), client


def _empty_query_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"QueryResponse": {}})


def _create_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"Customer": QBO_CUSTOMER_RECORD})


def _read_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"Customer": QBO_CUSTOMER_RECORD})


def test_full_create_and_read_back_flow_success(settings):
    transport = ScriptedTransport(
        [
            ("GET", "/query", _empty_query_response, -1),
            ("POST", "/customer", _create_response, -1),
            ("GET", "/customer/100", _read_response, -1),
        ]
    )
    service, client = _build_service(settings, transport)
    customer = CanonicalCustomer(external_id="ext-1", display_name="Acme Corp")

    result = service.sync_customer(customer, approve=lambda c: True)

    assert result.status == "created"
    assert result.customer.erp_id == "100"
    assert IdempotencyStore(settings.idempotency_store_path).get("ext-1") == "100"
    client.close()


def test_second_sync_uses_local_idempotency_store_and_skips_create(settings):
    IdempotencyStore(settings.idempotency_store_path).put("ext-1", "100")
    transport = ScriptedTransport([("GET", "/customer/100", _read_response, -1)])
    service, client = _build_service(settings, transport)
    customer = CanonicalCustomer(external_id="ext-1", display_name="Acme Corp")

    result = service.sync_customer(customer, approve=lambda c: pytest.fail("should not need approval"))

    assert result.status == "already_exists"
    assert all(r.method != "POST" for r in transport.requests)
    client.close()


def test_live_duplicate_match_short_circuits_create(settings):
    def _match_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"QueryResponse": {"Customer": [QBO_CUSTOMER_RECORD]}})

    transport = ScriptedTransport([("GET", "/query", _match_response, -1)])
    service, client = _build_service(settings, transport)
    customer = CanonicalCustomer(external_id="ext-1", display_name="Acme Corp")

    result = service.sync_customer(customer, approve=lambda c: pytest.fail("should not need approval"))

    assert result.status == "already_exists"
    assert IdempotencyStore(settings.idempotency_store_path).get("ext-1") == "100"
    assert all(r.method != "POST" for r in transport.requests)
    client.close()


def test_human_rejects_approval_aborts_before_any_write(settings):
    transport = ScriptedTransport([("GET", "/query", _empty_query_response, -1)])
    service, client = _build_service(settings, transport)
    customer = CanonicalCustomer(external_id="ext-1", display_name="Acme Corp")

    result = service.sync_customer(customer, approve=lambda c: False)

    assert result.status == "rejected_by_human"
    assert all(r.method != "POST" for r in transport.requests)
    client.close()


def test_transient_429_on_create_is_retried_then_succeeds(settings):
    call_count = {"n": 0}

    def _flaky_create(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return httpx.Response(200, json={"Customer": QBO_CUSTOMER_RECORD})

    transport = ScriptedTransport(
        [
            ("GET", "/query", _empty_query_response, -1),
            ("POST", "/customer", _flaky_create, -1),
            ("GET", "/customer/100", _read_response, -1),
        ]
    )
    service, client = _build_service(settings, transport)
    customer = CanonicalCustomer(external_id="ext-1", display_name="Acme Corp")

    result = service.sync_customer(customer, approve=lambda c: True)

    assert result.status == "created"
    assert call_count["n"] == 2
    client.close()


def test_401_on_create_surfaces_auth_error_without_retrying(settings):
    call_count = {"n": 0}

    def _unauthorized(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(401, json={})

    transport = ScriptedTransport(
        [
            ("GET", "/query", _empty_query_response, -1),
            ("POST", "/customer", _unauthorized, -1),
        ]
    )
    service, client = _build_service(settings, transport)
    customer = CanonicalCustomer(external_id="ext-1", display_name="Acme Corp")

    with pytest.raises(ERPAuthError):
        service.sync_customer(customer, approve=lambda c: True)

    assert call_count["n"] == 1
    client.close()


def test_verify_connection_reads_company_info(settings):
    def _company_info(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"CompanyInfo": {"CompanyName": "Sandbox Co", "Id": "1"}})

    transport = ScriptedTransport([("GET", "/companyinfo/", _company_info, -1)])
    token_store = _seed_valid_token(settings)
    client = QBOClient(settings, token_store, transport=transport)

    info = client.verify_connection()

    assert info["CompanyName"] == "Sandbox Co"
    client.close()
