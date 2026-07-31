"""SQLAlchemy ORM models for the hosted web app.

These replace the CLI's flat-file stores (`idempotency.py`, `audit.py`,
`qbo_auth.TokenStore`) for hosted use, per the requirement to use a real
database rather than local JSON files once this runs on a server with
ephemeral/shared disk. The CLI is untouched and keeps using its files.

Security note: `QboConnection.access_token` / `.refresh_token` are stored
as plain columns, same trust model as the CLI's local token-cache file.
Encrypting them at the column level is listed as a documented limitation
in REPORT.md rather than implemented here — see "Security limitations."
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QboConnection(Base):
    """The single active QBO connection. Only one row should ever exist;
    reconnecting replaces it rather than adding a second one."""

    __tablename__ = "qbo_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    realm_id: Mapped[str] = mapped_column(String(64))
    company_name: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text)
    expires_at_epoch: Mapped[float] = mapped_column()
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ActivityLog(Base):
    """Append-only activity history. Never store tokens, secrets, or full
    API payloads here — only IDs and a safe, human-readable outcome."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128))
    qbo_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    outcome: Mapped[str] = mapped_column(String(64))
    error_summary: Mapped[Optional[str]] = mapped_column(String(500), default=None)


class ExternalIdMap(Base):
    """Local idempotency map: (entity_type, external_id) -> QBO Id."""

    __tablename__ = "external_id_map"
    __table_args__ = (UniqueConstraint("entity_type", "external_id", name="uq_entity_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128))
    qbo_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BulkUploadJob(Base):
    """A CSV bulk-upload run: parsed+validated rows, then (after human
    confirmation) the per-row processing results. Persisted in the
    database rather than kept in memory so the upload -> preview ->
    confirm flow survives a cold start on Render's free tier."""

    __tablename__ = "bulk_upload_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending_confirmation")
    row_count: Mapped[int] = mapped_column(default=0)
    rows_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    results_json: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
