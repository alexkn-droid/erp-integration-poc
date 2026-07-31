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


def test_invalid_email_rejected():
    with pytest.raises(ValidationError):
        CanonicalCustomer(external_id="ext-1", display_name="Acme", email="not-an-email")


def test_currency_normalized_to_uppercase():
    c = CanonicalCustomer(external_id="ext-1", display_name="Acme", currency="usd")
    assert c.currency == "USD"


def test_external_id_required():
    with pytest.raises(ValidationError):
        CanonicalCustomer(external_id="", display_name="Acme")
