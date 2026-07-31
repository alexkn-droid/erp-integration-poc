"""Thin HTTP client for the QBO Accounting API v3 (Customer/Vendor + CompanyInfo).

All network calls funnel through `_request`, which is where auth-header
injection, JSON-vs-fault-body parsing, and error normalization happen
exactly once. Callers (service.py) never touch httpx directly.

Customer and Vendor are handled by the same generic `*_entity` methods,
parametrized by `entity_type` ("customer" or "vendor") — QBO uses an
identical REST shape for both (`/​{entity_type}`, JSON key
`{entity_type.capitalize()}`). `get_customer`/`create_customer`/etc. are
kept as thin named wrappers so existing CLI code and tests are unaffected.

The CLI targets one fixed realm from `.env` (`settings.qbo_realm_id`); the
web app targets whichever realm the current QBO connection points at,
which can change if an admin disconnects/reconnects — so `realm_id` can
be passed explicitly and takes precedence when it is.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from .errors import ERPNetworkError, normalize_qbo_error
from .qbo_auth import TokenStore, get_valid_access_token
from .settings import BaseQboSettings


class QBOClient:
    def __init__(
        self,
        settings: BaseQboSettings,
        token_store: TokenStore,
        *,
        realm_id: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._settings = settings
        self._token_store = token_store
        self._realm_id = realm_id if realm_id is not None else getattr(settings, "qbo_realm_id", None)
        if not self._realm_id:
            raise ValueError("QBOClient requires a realm_id (pass explicitly, or via settings.qbo_realm_id)")
        self._http = httpx.Client(transport=transport, timeout=30.0)

    def close(self) -> None:
        self._http.close()

    def verify_connection(self) -> dict[str, Any]:
        """Calls CompanyInfo — the standard "is auth working at all" smoke test."""
        return self._request("GET", f"/companyinfo/{self._realm_id}")["CompanyInfo"]

    # --- Generic entity operations (Customer, Vendor) ---

    def get_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        return self._request("GET", f"/{entity_type}/{entity_id}")[_json_key(entity_type)]

    def find_entity_by_display_name(self, entity_type: str, display_name: str) -> Optional[dict[str, Any]]:
        escaped = _escape_query_literal(display_name)
        query = f"select * from {_json_key(entity_type)} where DisplayName = '{escaped}'"
        result = self._request("GET", "/query", params={"query": query})
        matches = result.get("QueryResponse", {}).get(_json_key(entity_type), [])
        return matches[0] if matches else None

    def search_entities(self, entity_type: str, *, name_contains: str = "", max_results: int = 25) -> list[dict[str, Any]]:
        max_results = max(1, min(max_results, 100))
        if name_contains:
            escaped = _escape_query_literal(name_contains)
            query = f"select * from {_json_key(entity_type)} where DisplayName like '%{escaped}%' maxresults {max_results}"
        else:
            query = f"select * from {_json_key(entity_type)} maxresults {max_results}"
        result = self._request("GET", "/query", params={"query": query})
        return result.get("QueryResponse", {}).get(_json_key(entity_type), [])

    def create_entity(self, entity_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/{entity_type}", json=payload)[_json_key(entity_type)]

    def update_entity(self, entity_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """`payload` must include `Id` and the current `SyncToken` (QBO uses POST for updates too)."""
        return self._request("POST", f"/{entity_type}", json=payload)[_json_key(entity_type)]

    # --- Named wrappers kept for backward compatibility with the CLI ---

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        return self.get_entity("customer", customer_id)

    def find_customer_by_display_name(self, display_name: str) -> Optional[dict[str, Any]]:
        return self.find_entity_by_display_name("customer", display_name)

    def create_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.create_entity("customer", payload)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        access_token = get_valid_access_token(self._settings, self._token_store)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"

        url = f"{self._settings.accounting_api_base_url_for(self._realm_id)}{path}"
        try:
            response = self._http.request(method, url, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            raise ERPNetworkError(f"Timed out calling QBO: {exc}") from exc
        except httpx.TransportError as exc:
            raise ERPNetworkError(f"Network error calling QBO: {exc}") from exc

        if response.status_code >= 400:
            body = _safe_json(response)
            raise normalize_qbo_error(
                http_status=response.status_code,
                body=body,
                retry_after_header=response.headers.get("Retry-After"),
            )
        return _safe_json(response) or {}


def _json_key(entity_type: str) -> str:
    """QBO's JSON envelope key for an entity type, e.g. "customer" -> "Customer"."""
    return entity_type[:1].upper() + entity_type[1:]


def _escape_query_literal(value: str) -> str:
    return value.replace("'", r"\'")


def _safe_json(response: httpx.Response) -> Optional[dict[str, Any]]:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None
