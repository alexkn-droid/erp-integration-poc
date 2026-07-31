"""Canonical (ERP-agnostic) data model.

This is the shape our system speaks internally. Every ERP connector is
responsible for translating to/from this shape in its own `transform_*`
module. Nothing outside the connector layer should ever import an
ERP-specific schema — that boundary is what makes a second connector
(NetSuite, Xero, ...) additive rather than a rewrite.

`CanonicalCustomer` and `CanonicalVendor` are both QBO "Name List"-style
parties with an identical field set (QBO's Customer and Vendor entities
happen to share the same shape), so the shared fields and validation live
once on `CanonicalParty`. Keeping them as distinct subclasses (rather than
one model with an `entity_type` flag) is deliberate: it keeps type hints
precise in the web layer (a customer form can never accidentally submit a
vendor) even though today they're identical in every other way.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class CanonicalAddress(BaseModel):
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class CanonicalParty(BaseModel):
    """Shared shape for a QBO Customer or Vendor master-data record.

    `external_id` is OUR system's identifier for this record and is the
    key used for idempotent create (see idempotency.py / ExternalIdMap).
    `erp_id` and `erp_sync_token` are populated once the record exists in
    the ERP and are ERP-opaque — callers should not need to know their
    format. `erp_sync_token` is required by QBO on every update request
    (optimistic-concurrency check) but is never sent on create.
    """

    external_id: str = Field(..., min_length=1, description="Our system's stable ID for this record")
    display_name: str = Field(..., min_length=1, max_length=100)
    company_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    billing_address: Optional[CanonicalAddress] = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    is_active: bool = True

    erp_id: Optional[str] = None
    erp_sync_token: Optional[str] = None

    @field_validator("display_name")
    @classmethod
    def display_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be blank")
        return v

    @field_validator("currency")
    @classmethod
    def currency_upper(cls, v: str) -> str:
        return v.upper()


class CanonicalCustomer(CanonicalParty):
    """A minimal customer master-data record. See CanonicalParty for fields."""


class CanonicalVendor(CanonicalParty):
    """A minimal vendor master-data record. See CanonicalParty for fields."""
