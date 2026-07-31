"""Shared browser workflow for a QBO "Name List" entity (Customer or Vendor).

Both `routers/customers.py` and `routers/vendors.py` are thin — a handful
of `@router` route declarations each, all delegating straight into the
functions here with `entity_type`/`model_cls` fixed. All actual behavior
(form parsing/validation, the review-and-confirm step, duplicate
detection, error handling) lives exactly once. Both routers also render
the same `templates/party/*.html` files — there is nothing customer- or
vendor-specific about the markup, only the `label`/`url_prefix` values
passed into the template context.
"""

from __future__ import annotations

import uuid
from typing import Mapping, Optional, Type

from fastapi import Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..canonical import CanonicalAddress, CanonicalParty
from ..errors import ERPError
from .deps import redirect_with_message, require_csrf, require_sandbox_environment
from .messages import plain_language_message
from .qbo import build_party_service, get_qbo_client_or_none
from .templating import render


def _no_connection_response() -> RedirectResponse:
    return RedirectResponse(
        url=redirect_with_message("/connection", "QuickBooks is not connected. Connect it first.", level="warning"),
        status_code=303,
    )


def build_party_from_mapping(
    model_cls: Type[CanonicalParty], form: Mapping[str, str], *, external_id: str
) -> tuple[Optional[CanonicalParty], list[str]]:
    """`form` just needs `.get(key, default)` — a Starlette FormData (web forms)
    or a plain dict (a parsed CSV row, see routers/bulk.py) both work."""
    address_present = any(form.get(f) for f in ("address_line1", "address_line2", "city", "state", "postal_code", "country"))
    address = None
    if address_present:
        address = CanonicalAddress(
            line1=(form.get("address_line1") or None),
            line2=(form.get("address_line2") or None),
            city=(form.get("city") or None),
            state=(form.get("state") or None),
            postal_code=(form.get("postal_code") or None),
            country=(form.get("country") or None),
        )
    try:
        party = model_cls(
            external_id=external_id,
            display_name=form.get("display_name", ""),
            company_name=(form.get("company_name") or None),
            email=(form.get("email") or None),
            phone=(form.get("phone") or None),
            billing_address=address,
            currency=(form.get("currency") or "USD"),
            is_active=(form.get("is_active") == "on"),
        )
        return party, []
    except ValidationError as exc:
        return None, [f"{err['loc'][-1]}: {err['msg']}" for err in exc.errors()]


class PartyWeb:
    def __init__(self, *, entity_type: str, model_cls: Type[CanonicalParty], label: str, url_prefix: str):
        self.entity_type = entity_type
        self.model_cls = model_cls
        self.label = label
        self.url_prefix = url_prefix

    def _ctx(self, **extra) -> dict:
        return {"label": self.label, "url_prefix": self.url_prefix, **extra}

    # ---- list / search ----

    def list_view(self, request: Request, db: Session, session: dict, q: str):
        client = get_qbo_client_or_none(request, db)
        if client is None:
            return render(request, "party/list.html", session=session, results=[], q=q, **self._ctx(connected=False))
        try:
            service = build_party_service(
                entity_type=self.entity_type, model_cls=self.model_cls, web_settings=request.app.state.web_settings, client=client, db=db
            )
            results = service.search(name_contains=q, max_results=25)
        finally:
            client.close()
        return render(request, "party/list.html", session=session, results=results, q=q, **self._ctx(connected=True))

    # ---- detail ----

    def detail_view(self, request: Request, db: Session, session: dict, erp_id: str):
        client = get_qbo_client_or_none(request, db)
        if client is None:
            return _no_connection_response()
        try:
            service = build_party_service(
                entity_type=self.entity_type, model_cls=self.model_cls, web_settings=request.app.state.web_settings, client=client, db=db
            )
            party = service.read(erp_id=erp_id, external_id=erp_id)
        finally:
            client.close()
        return render(request, "party/detail.html", session=session, party=party, **self._ctx())

    # ---- create ----

    def new_form(self, request: Request, session: dict):
        return render(
            request,
            "party/form.html",
            session=session,
            mode="create",
            erp_id=None,
            errors=[],
            form_values={"external_id": str(uuid.uuid4()), "currency": "USD", "is_active": "on"},
            **self._ctx(),
        )

    async def create_submit(self, request: Request, db: Session, session: dict):
        form = await request.form()
        require_csrf(session, str(form.get("csrf_token", "")))
        require_sandbox_environment(request.app.state.web_settings)

        confirmed = form.get("confirm") == "yes"
        external_id = str(form.get("external_id") or uuid.uuid4())
        party, errors = build_party_from_mapping(self.model_cls, form, external_id=external_id)

        if errors or party is None:
            return render(
                request, "party/form.html", session=session, mode="create", erp_id=None,
                errors=errors, form_values=form, status_code=400, **self._ctx(),
            )

        if not confirmed:
            return render(request, "party/confirm.html", session=session, mode="create", erp_id=None, party=party, form=form, **self._ctx())

        client = get_qbo_client_or_none(request, db)
        if client is None:
            return _no_connection_response()
        try:
            service = build_party_service(
                entity_type=self.entity_type, model_cls=self.model_cls, web_settings=request.app.state.web_settings, client=client, db=db
            )
            try:
                result = service.sync(party, approve=lambda p: True)
            except ERPError as exc:
                return render(
                    request, "party/form.html", session=session, mode="create", erp_id=None,
                    errors=[plain_language_message(exc)], form_values=form, status_code=502, **self._ctx(),
                )
        finally:
            client.close()

        return self._sync_result_redirect(result)

    # ---- update ----

    def edit_form(self, request: Request, db: Session, session: dict, erp_id: str):
        client = get_qbo_client_or_none(request, db)
        if client is None:
            return _no_connection_response()
        try:
            service = build_party_service(
                entity_type=self.entity_type, model_cls=self.model_cls, web_settings=request.app.state.web_settings, client=client, db=db
            )
            party = service.read(erp_id=erp_id, external_id=erp_id)
        finally:
            client.close()

        addr = party.billing_address
        form_values = {
            "external_id": party.external_id,
            "display_name": party.display_name,
            "company_name": party.company_name or "",
            "email": party.email or "",
            "phone": party.phone or "",
            "address_line1": addr.line1 if addr else "",
            "address_line2": addr.line2 if addr else "",
            "city": addr.city if addr else "",
            "state": addr.state if addr else "",
            "postal_code": addr.postal_code if addr else "",
            "country": addr.country if addr else "",
            "currency": party.currency,
            "is_active": "on" if party.is_active else "",
        }
        return render(
            request, "party/form.html", session=session, mode="edit", erp_id=erp_id,
            errors=[], form_values=form_values, **self._ctx(),
        )

    async def edit_submit(self, request: Request, db: Session, session: dict, erp_id: str):
        form = await request.form()
        require_csrf(session, str(form.get("csrf_token", "")))
        require_sandbox_environment(request.app.state.web_settings)

        confirmed = form.get("confirm") == "yes"
        external_id = str(form.get("external_id") or erp_id)
        party, errors = build_party_from_mapping(self.model_cls, form, external_id=external_id)

        if errors or party is None:
            return render(
                request, "party/form.html", session=session, mode="edit", erp_id=erp_id,
                errors=errors, form_values=form, status_code=400, **self._ctx(),
            )

        if not confirmed:
            return render(request, "party/confirm.html", session=session, mode="edit", erp_id=erp_id, party=party, form=form, **self._ctx())

        client = get_qbo_client_or_none(request, db)
        if client is None:
            return _no_connection_response()
        try:
            service = build_party_service(
                entity_type=self.entity_type, model_cls=self.model_cls, web_settings=request.app.state.web_settings, client=client, db=db
            )
            try:
                result = service.update(erp_id=erp_id, party=party, approve=lambda p: True)
            except ERPError as exc:
                return render(
                    request, "party/form.html", session=session, mode="edit", erp_id=erp_id,
                    errors=[plain_language_message(exc)], form_values=form, status_code=502, **self._ctx(),
                )
        finally:
            client.close()

        return self._sync_result_redirect(result)

    def _sync_result_redirect(self, result):
        if result.status == "created":
            msg, level = f"{self.label} created successfully.", "success"
        elif result.status == "updated":
            msg, level = f"{self.label} updated successfully.", "success"
        elif result.status == "already_exists":
            msg, level = f"This {self.label.lower()} already exists in QuickBooks — showing the existing record.", "warning"
        else:
            msg, level = "No changes were made.", "warning"

        target = f"{self.url_prefix}/{result.party.erp_id}" if result.party else self.url_prefix
        return RedirectResponse(url=redirect_with_message(target, msg, level=level), status_code=303)
