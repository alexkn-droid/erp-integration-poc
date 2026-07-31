"""Web app configuration.

Separate from the CLI's `erp_poc.settings.Settings` because the web app
has no fixed realm ID (it's discovered via the browser OAuth flow and
stored in the database — see models_db.QboConnection) and has its own
secrets (session signing key, shared-password hash, database URL) that
the CLI has no use for. Both share `BaseQboSettings` for the QBO client
credentials themselves, so there's exactly one place that logic lives.
"""

from __future__ import annotations

from pydantic import Field

from ..settings import BaseQboSettings


class WebSettings(BaseQboSettings):
    app_secret_key: str = Field(..., min_length=16, description="Signs session cookies and CSRF tokens")
    shared_password_hash: str = Field(..., description="passlib pbkdf2_sha256 hash; generate with scripts/generate_secrets.py")
    database_url: str = Field(..., description="SQLAlchemy URL, e.g. postgresql+psycopg://... or sqlite:///./.state/web.db")

    max_retries: int = 5
    retry_base_delay_seconds: float = 1.0

    session_max_age_seconds: int = 12 * 60 * 60  # 12 hours
    max_upload_rows: int = 500
    max_upload_bytes: int = 2 * 1024 * 1024  # 2 MB


def get_web_settings() -> WebSettings:
    return WebSettings()  # type: ignore[call-arg]  # values come from environment / .env
