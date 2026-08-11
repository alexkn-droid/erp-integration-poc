from __future__ import annotations

import pytest
from pydantic import ValidationError

from erp_poc.canonical import CanonicalCustomer


def test_minimal_valid_customer():
    c = CanonicalCustomer(external_id="ext-1", display_name="Acme Corp")
    assert c.currency == "USD"
    assert c.is_active is True
    assert c.erp_id is None


def test_display_name_required():
    with pytest.raises(ValidationError):
        CanonicalCustomer(external_id="ext-1", display_name="")


def test_display_name_whitespace_only_rejected():
    with pytest.raises(ValidationError):
        CanonicalCustomer(external_id="ext-1", display_name="   ")


def test_email_is_not_strictly_format_validated():
    """Deliberate: QBO's own data doesn't enforce RFC email format either — a
    live sandbox company's seeded sample data has a Vendor with two
    comma-separated addresses in this field, which QBO accepts. Enforcing a
    stricter rule than the ERP itself crashes when reading QBO's own real
    data back (this was an actual production bug, not a hypothetical)."""
    c = CanonicalCustomer(external_id="ext-1", display_name="Acme", email="a@x.com, b@x.com")
    assert c.email == "a@x.com, b@x.com"


def test_email_still_respects_max_length():
    with pytest.raises(ValidationError):
        CanonicalCustomer(external_id="ext-1", display_name="Acme", email="x" * 201)


def test_currency_normalized_to_uppercase():
    c = CanonicalCustomer(external_id="ext-1", display_name="Acme", currency="usd")
    assert c.currency == "USD"


def test_external_id_required():
    with pytest.raises(ValidationError):
        CanonicalCustomer(external_id="", display_name="Acme")
