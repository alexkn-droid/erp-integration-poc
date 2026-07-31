from __future__ import annotations

from erp_poc.canonical import CanonicalAddress, CanonicalCustomer
from erp_poc.transform_qbo import canonical_to_qbo_payload, qbo_customer_to_canonical

FULL_QBO_CUSTOMER = {
    "Id": "42",
    "SyncToken": "0",
    "DisplayName": "Acme Corp",
    "CompanyName": "Acme Corporation",
    "PrimaryEmailAddr": {"Address": "ap@acme-example.com"},
    "PrimaryPhone": {"FreeFormNumber": "+1-555-0100"},
    "CurrencyRef": {"value": "USD", "name": "United States Dollar"},
    "Active": True,
    "BillAddr": {
        "Line1": "123 Main St",
        "City": "Springfield",
        "CountrySubDivisionCode": "IL",
        "PostalCode": "62701",
        "Country": "US",
    },
}


def test_canonical_to_qbo_payload_includes_all_provided_fields():
    customer = CanonicalCustomer(
        external_id="ext-1",
        display_name="Acme Corp",
        company_name="Acme Corporation",
        email="ap@acme-example.com",
        phone="+1-555-0100",
        currency="usd",
        billing_address=CanonicalAddress(line1="123 Main St", city="Springfield", state="IL", postal_code="62701", country="US"),
    )
    payload = canonical_to_qbo_payload(customer)
    assert payload["DisplayName"] == "Acme Corp"
    assert payload["PrimaryEmailAddr"] == {"Address": "ap@acme-example.com"}
    assert payload["CurrencyRef"] == {"value": "USD"}
    assert payload["BillAddr"]["CountrySubDivisionCode"] == "IL"


def test_canonical_to_qbo_payload_omits_absent_optional_fields():
    customer = CanonicalCustomer(external_id="ext-1", display_name="Minimal Co")
    payload = canonical_to_qbo_payload(customer)
    assert "PrimaryEmailAddr" not in payload
    assert "BillAddr" not in payload
    assert payload["DisplayName"] == "Minimal Co"


def test_qbo_customer_to_canonical_round_trip():
    canonical = qbo_customer_to_canonical(FULL_QBO_CUSTOMER, external_id="ext-1")
    assert canonical.erp_id == "42"
    assert canonical.erp_sync_token == "0"
    assert canonical.email == "ap@acme-example.com"
    assert canonical.billing_address.state == "IL"
    assert canonical.currency == "USD"


def test_qbo_customer_to_canonical_handles_missing_optional_fields():
    minimal = {"Id": "7", "SyncToken": "0", "DisplayName": "Bare Co"}
    canonical = qbo_customer_to_canonical(minimal, external_id="ext-2")
    assert canonical.email is None
    assert canonical.billing_address is None
    assert canonical.currency == "USD"
    assert canonical.is_active is True
