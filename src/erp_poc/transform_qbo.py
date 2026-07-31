"""Bidirectional mapping between QBO JSON and CanonicalParty (Customer/Vendor).

This is the ONLY file that should know QBO's field names. Field mapping
decisions and their sources are documented in REPORT.md (Phase 3 /
Technical Design), not here — keep this module focused on the mechanics.

QBO's Customer and Vendor entities share an identical field set for
everything this PoC maps (DisplayName, CompanyName, PrimaryEmailAddr,
PrimaryPhone, BillAddr, CurrencyRef, Active, Id, SyncToken), so one pair
of generic functions serves both — `canonical_to_qbo_payload` /
`qbo_customer_to_canonical` are kept as thin, named wrappers so existing
CLI code and tests importing them by name are unaffected.
"""

from __future__ import annotations

from typing import Any, Optional, TypeVar

from .canonical import CanonicalAddress, CanonicalCustomer, CanonicalParty, CanonicalVendor

PartyT = TypeVar("PartyT", bound=CanonicalParty)


def party_to_qbo_payload(party: CanonicalParty) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "DisplayName": party.display_name,
        "Active": party.is_active,
    }
    if party.company_name:
        payload["CompanyName"] = party.company_name
    if party.email:
        payload["PrimaryEmailAddr"] = {"Address": party.email}
    if party.phone:
        payload["PrimaryPhone"] = {"FreeFormNumber": party.phone}
    if party.currency:
        payload["CurrencyRef"] = {"value": party.currency}
    if party.billing_address:
        payload["BillAddr"] = _address_to_qbo(party.billing_address)
    return payload


def qbo_data_to_party(data: dict[str, Any], *, external_id: str, model_cls: type[PartyT]) -> PartyT:
    bill_addr = data.get("BillAddr")
    return model_cls(
        external_id=external_id,
        display_name=data["DisplayName"],
        company_name=data.get("CompanyName"),
        email=(data.get("PrimaryEmailAddr") or {}).get("Address"),
        phone=(data.get("PrimaryPhone") or {}).get("FreeFormNumber"),
        billing_address=_address_from_qbo(bill_addr) if bill_addr else None,
        currency=(data.get("CurrencyRef") or {}).get("value", "USD"),
        is_active=data.get("Active", True),
        erp_id=str(data["Id"]),
        erp_sync_token=data.get("SyncToken"),
    )


# --- Named wrappers kept for backward compatibility with the CLI and its tests ---


def canonical_to_qbo_payload(customer: CanonicalCustomer) -> dict[str, Any]:
    return party_to_qbo_payload(customer)


def qbo_customer_to_canonical(data: dict[str, Any], *, external_id: str) -> CanonicalCustomer:
    return qbo_data_to_party(data, external_id=external_id, model_cls=CanonicalCustomer)


def qbo_vendor_to_canonical(data: dict[str, Any], *, external_id: str) -> CanonicalVendor:
    return qbo_data_to_party(data, external_id=external_id, model_cls=CanonicalVendor)


def _address_to_qbo(address: CanonicalAddress) -> dict[str, Any]:
    qbo_addr: dict[str, Any] = {}
    if address.line1:
        qbo_addr["Line1"] = address.line1
    if address.line2:
        qbo_addr["Line2"] = address.line2
    if address.city:
        qbo_addr["City"] = address.city
    if address.state:
        qbo_addr["CountrySubDivisionCode"] = address.state
    if address.postal_code:
        qbo_addr["PostalCode"] = address.postal_code
    if address.country:
        qbo_addr["Country"] = address.country
    return qbo_addr


def _address_from_qbo(data: Optional[dict[str, Any]]) -> Optional[CanonicalAddress]:
    if not data:
        return None
    return CanonicalAddress(
        line1=data.get("Line1"),
        line2=data.get("Line2"),
        city=data.get("City"),
        state=data.get("CountrySubDivisionCode"),
        postal_code=data.get("PostalCode"),
        country=data.get("Country"),
    )
