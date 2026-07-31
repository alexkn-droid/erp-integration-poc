"""Database-backed equivalents of the CLI's flat-file stores.

Each class here duck-types the interface the CLI's file-based version
exposes (`qbo_auth.TokenStore`, `idempotency.IdempotencyStore`,
`audit.AuditTrail`), so `qbo_auth.get_valid_access_token()` and
`service.PartySyncService` work unmodified against either — the only
difference is where the data actually lives.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..qbo_auth import TokenSet
from .models_db import ActivityLog, ExternalIdMap, QboConnection

# Safety cap so a runaway error message can never blow up a DB column or,
# worse, accidentally carry something sensitive-looking into a log row.
_ERROR_SUMMARY_MAX_LEN = 300


class DbTokenStore:
    """Backs the single shared QBO connection. Duck-types qbo_auth.TokenStore."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def load(self) -> Optional[TokenSet]:
        row = self._current_row()
        if row is None:
            return None
        return TokenSet(access_token=row.access_token, refresh_token=row.refresh_token, expires_at_epoch=row.expires_at_epoch)

    def save(self, tokens: TokenSet) -> None:
        row = self._current_row()
        if row is None:
            raise RuntimeError("No QboConnection row exists yet — call save_new_connection() from the OAuth callback first.")
        row.access_token = tokens.access_token
        row.refresh_token = tokens.refresh_token
        row.expires_at_epoch = tokens.expires_at_epoch
        self._db.commit()

    def save_new_connection(self, *, realm_id: str, company_name: Optional[str], tokens: TokenSet) -> QboConnection:
        """Used only by the OAuth callback route: replaces any existing connection
        (there is only ever one — see QboConnection's docstring)."""
        self._db.execute(delete(QboConnection))
        row = QboConnection(
            realm_id=realm_id,
            company_name=company_name,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_at_epoch=tokens.expires_at_epoch,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def disconnect(self) -> None:
        self._db.execute(delete(QboConnection))
        self._db.commit()

    def current_connection(self) -> Optional[QboConnection]:
        return self._current_row()

    def _current_row(self) -> Optional[QboConnection]:
        return self._db.execute(select(QboConnection).order_by(QboConnection.id.desc())).scalars().first()


class DbIdempotencyStore:
    """One instance per entity_type ("customer"/"vendor"). Duck-types idempotency.IdempotencyStore."""

    def __init__(self, db: Session, *, entity_type: str) -> None:
        self._db = db
        self._entity_type = entity_type

    def get(self, external_id: str) -> Optional[str]:
        row = self._db.execute(
            select(ExternalIdMap).where(
                ExternalIdMap.entity_type == self._entity_type,
                ExternalIdMap.external_id == external_id,
            )
        ).scalar_one_or_none()
        return row.qbo_id if row else None

    def put(self, external_id: str, erp_id: str) -> None:
        existing = self._db.execute(
            select(ExternalIdMap).where(
                ExternalIdMap.entity_type == self._entity_type,
                ExternalIdMap.external_id == external_id,
            )
        ).scalar_one_or_none()
        if existing:
            existing.qbo_id = erp_id
        else:
            self._db.add(ExternalIdMap(entity_type=self._entity_type, external_id=external_id, qbo_id=erp_id))
        self._db.commit()


class DbAuditTrail:
    """Duck-types audit.AuditTrail, writing to the activity_log table instead of a file."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def record(
        self,
        *,
        action: str,
        object_type: str,
        external_id: str,
        erp_id: Optional[str],
        result: str,
        human_approved: bool,
        detail: Optional[dict] = None,
    ) -> None:
        error_summary = None
        if detail and detail.get("error"):
            error_summary = str(detail["error"])[:_ERROR_SUMMARY_MAX_LEN]
        self._db.add(
            ActivityLog(
                action=action,
                entity_type=object_type,
                external_id=external_id,
                qbo_id=erp_id,
                outcome=result,
                error_summary=error_summary,
            )
        )
        self._db.commit()
