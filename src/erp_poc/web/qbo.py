"""Builds a QBOClient bound to whatever the current DB-stored connection is.

Kept separate from deps.py because it needs both a DB session and access
to the app's (possibly test-overridden) transport, and is used by several
routers (customers, vendors, bulk, connection health-check).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from ..canonical import CanonicalParty
from ..qbo_client import QBOClient
from ..service import PartySyncService
from .models_db import QboConnection
from .stores import DbAuditTrail, DbIdempotencyStore, DbTokenStore


@dataclass
class ConnectionStatus:
    connected: bool
    realm_id: Optional[str] = None
    company_name: Optional[str] = None
    connected_at: Optional[str] = None


def get_connection_status(db: Session) -> ConnectionStatus:
    row = DbTokenStore(db).current_connection()
    if row is None:
        return ConnectionStatus(connected=False)
    return ConnectionStatus(
        connected=True,
        realm_id=row.realm_id,
        company_name=row.company_name,
        connected_at=row.connected_at.isoformat() if row.connected_at else None,
    )


def get_qbo_client_or_none(request: Request, db: Session) -> Optional[QBOClient]:
    row: Optional[QboConnection] = DbTokenStore(db).current_connection()
    if row is None:
        return None
    return QBOClient(
        request.app.state.web_settings,
        DbTokenStore(db),
        realm_id=row.realm_id,
        transport=getattr(request.app.state, "qbo_transport", None),
    )


def build_party_service(
    *,
    entity_type: str,
    model_cls: type[CanonicalParty],
    web_settings,
    client: QBOClient,
    db: Session,
) -> PartySyncService:
    return PartySyncService(
        web_settings,
        client,
        DbIdempotencyStore(db, entity_type=entity_type),
        DbAuditTrail(db),
        entity_type=entity_type,
        model_cls=model_cls,
    )
