"""OAuth2 token lifecycle for QuickBooks Online.

QBO uses the 3-legged OAuth2 authorization-code grant: a human must
authorize the app in a browser (this cannot be automated and is not
attempted here — see scripts/initial_oauth_exchange.py and
docs/sandbox_test_procedure.md). Once an initial refresh token exists,
this module handles the parts that ARE safe to automate: checking
access-token expiry and refreshing.

Important QBO-specific behavior this module has to account for:
  - Access tokens last ~1 hour.
  - Refresh tokens are *rotating* and single-use: every refresh call
    returns a NEW refresh token, and the old one stops working. The
    token store must be overwritten atomically on every refresh, or a
    crash between "got new token" and "saved new token" strands the
    connector and forces a human to re-authorize from scratch.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from .errors import ERPAuthError
from .settings import Settings


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at_epoch: float

    def is_expired(self, *, skew_seconds: float = 60.0) -> bool:
        return time.time() >= (self.expires_at_epoch - skew_seconds)


class TokenStore:
    """Reads/writes the token cache file. Never logs its contents."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Optional[TokenSet]:
        if not self._path.exists():
            return None
        with self._path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return TokenSet(**data)

    def save(self, tokens: TokenSet) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(tokens.__dict__, f)
        tmp_path.replace(self._path)  # atomic on POSIX


def exchange_code_for_tokens(settings: Settings, *, authorization_code: str) -> TokenSet:
    """One-time exchange of the browser-consent code for the first token pair.

    This is invoked by scripts/initial_oauth_exchange.py, which a human
    runs manually after completing the OAuth consent screen. It is not
    called anywhere in the normal read/write flow.
    """
    response = httpx.post(
        settings.oauth_token_url,
        headers=_basic_auth_header(settings),
        data={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": settings.qbo_redirect_uri,
        },
        timeout=30.0,
    )
    return _parse_token_response(response)


def get_valid_access_token(settings: Settings, store: TokenStore) -> str:
    tokens = store.load()
    if tokens is None:
        raise ERPAuthError(
            "No cached OAuth tokens found. A human must complete the QuickBooks "
            "Online consent flow first (see docs/sandbox_test_procedure.md)."
        )
    if tokens.is_expired():
        tokens = _refresh(settings, tokens)
        store.save(tokens)
    return tokens.access_token


def _refresh(settings: Settings, tokens: TokenSet) -> TokenSet:
    response = httpx.post(
        settings.oauth_token_url,
        headers=_basic_auth_header(settings),
        data={"grant_type": "refresh_token", "refresh_token": tokens.refresh_token},
        timeout=30.0,
    )
    if response.status_code == 401:
        raise ERPAuthError(
            "Refresh token was rejected (expired after ~100 days of inactivity, or "
            "revoked). A human must re-authorize via the browser consent flow."
        )
    return _parse_token_response(response)


def _parse_token_response(response: httpx.Response) -> TokenSet:
    if response.status_code >= 400:
        raise ERPAuthError(f"OAuth token endpoint returned HTTP {response.status_code}: {response.text}")
    body = response.json()
    return TokenSet(
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        expires_at_epoch=time.time() + float(body.get("expires_in", 3600)),
    )


def _basic_auth_header(settings: Settings) -> dict[str, str]:
    raw = f"{settings.qbo_client_id}:{settings.qbo_client_secret}".encode("utf-8")
    return {
        "Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
