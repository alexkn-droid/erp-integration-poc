"""Vendor routes. All behavior lives in party_views.PartyWeb — this file
only wires FastAPI routes to it with entity_type="vendor" fixed.
See routers/customers.py for the (nearly identical) customer equivalent."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...canonical import CanonicalVendor
from ..deps import get_db, require_login
from ..party_views import PartyWeb

router = APIRouter(prefix="/vendors")
_web = PartyWeb(entity_type="vendor", model_cls=CanonicalVendor, label="Vendor", url_prefix="/vendors")


@router.get("")
def list_vendors(request: Request, q: str = "", db: Session = Depends(get_db), session: dict = Depends(require_login)):
    return _web.list_view(request, db, session, q)


@router.get("/new")
def new_vendor(request: Request, session: dict = Depends(require_login)):
    return _web.new_form(request, session)


@router.post("/new")
async def create_vendor(request: Request, db: Session = Depends(get_db), session: dict = Depends(require_login)):
    return await _web.create_submit(request, db, session)


@router.get("/{erp_id}")
def view_vendor(request: Request, erp_id: str, db: Session = Depends(get_db), session: dict = Depends(require_login)):
    return _web.detail_view(request, db, session, erp_id)


@router.get("/{erp_id}/edit")
def edit_vendor(request: Request, erp_id: str, db: Session = Depends(get_db), session: dict = Depends(require_login)):
    return _web.edit_form(request, db, session, erp_id)


@router.post("/{erp_id}/edit")
async def update_vendor(request: Request, erp_id: str, db: Session = Depends(get_db), session: dict = Depends(require_login)):
    return await _web.edit_submit(request, db, session, erp_id)
