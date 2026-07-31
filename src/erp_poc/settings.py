"""Configuration loaded from environment variables / a local .env file.

No secret ever has a hard-coded default. Anything security-sensitive is
required and will raise a clear validation error at startup if missing,
rather than silently falling back to something insecure.

`BaseQboSettings` holds everything about talking to QBO itself (client
credentials, environment, redirect URI) that's shared between the CLI
(`Settings`, below — one fixed realm from `.env`) and the web app
(`erp_poc.web.config.WebSettings` — realm ID is dynamic, discovered via
the browser OAuth flow and stored in the database, so it deliberately
does NOT appear here).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseQboSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    qbo_client_id: str = Field(..., description="OAuth2 client ID from the Intuit Developer app dashboard")
    qbo_client_secret: str = Field(..., description="OAuth2 client secret; never log this value")
    qbo_environment: Literal["sandbox", "production"] = "sandbox"
    qbo_redirect_uri: str = "http://localhost:8000/callback"

    @property
    def oauth_token_url(self) -> str:
        return "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    def accounting_api_base_url_for(self, realm_id: str) -> str:
        host = (
            "sandbox-quickbooks.api.intuit.com"
            if self.qbo_environment == "sandbox"
            else "quickbooks.api.intuit.com"
        )
        return f"https://{host}/v3/company/{realm_id}"


class Settings(BaseQboSettings):
    """CLI settings: one fixed sandbox realm, configured via `.env`."""

    qbo_realm_id: str = Field(..., description="QuickBooks Online company (realm) ID")

    qbo_token_store_path: Path = Path(".state/tokens.json")
    idempotency_store_path: Path = Path(".state/idempotency_store.json")
    audit_log_path: Path = Path(".state/audit.log")

    max_retries: int = 5
    retry_base_delay_seconds: float = 1.0

    @property
    def accounting_api_base_url(self) -> str:
        return self.accounting_api_base_url_for(self.qbo_realm_id)


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from environment / .env
