"""Password hashing, session cookies, and CSRF tokens.

This app has exactly one password (shared by every user of this internal
prototype — see README "Security limitations"). It is never stored in
plaintext; only its passlib pbkdf2_sha256 hash lives in an env var.

Sessions are a signed, timestamped cookie (itsdangerous), not a database
row — there's nothing per-user to store since everyone shares one login.
The cookie's signature prevents tampering; `max_age` on `.loads()|` in
`deps.py` enforces the session timeout.
"""

from __future__ import annotations

import hmac
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

_password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

SESSION_COOKIE_NAME = "erp_poc_session"
OAUTH_STATE_COOKIE_NAME = "erp_poc_oauth_state"


def hash_password(plaintext_password: str) -> str:
    return _password_context.hash(plaintext_password)


def verify_password(plaintext_password: str, password_hash: str) -> bool:
    try:
        return _password_context.verify(plaintext_password, password_hash)
    except ValueError:
        # Malformed hash in config — treat as "does not match", never crash the login page.
        return False


def generate_app_secret_key() -> str:
    return secrets.token_hex(32)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_tokens_match(form_token: str, session_token: str) -> bool:
    return bool(form_token) and bool(session_token) and hmac.compare_digest(form_token, session_token)


class SessionSigner:
    """Thin wrapper around itsdangerous so callers never touch the serializer directly."""

    def __init__(self, app_secret_key: str, *, max_age_seconds: int) -> None:
        self._serializer = URLSafeTimedSerializer(app_secret_key, salt="erp-poc-session")
        self._max_age_seconds = max_age_seconds

    def sign(self, payload: dict) -> str:
        return self._serializer.dumps(payload)

    def unsign(self, cookie_value: str) -> dict | None:
        """Returns None (never raises) if the cookie is missing, tampered with, or expired."""
        try:
            return self._serializer.loads(cookie_value, max_age=self._max_age_seconds)
        except (BadSignature, SignatureExpired):
            return None


class OAuthStateSigner:
    """Separate, short-lived signer for the OAuth `state` cookie set at
    /connection/start and checked at /connection/callback. Deliberately
    independent of the login session cookie: the callback route does not
    require an active login session (see routers/qbo_connection.py), so
    CSRF protection on the OAuth round-trip has to stand on its own."""

    _MAX_AGE_SECONDS = 10 * 60  # the whole consent flow should take well under 10 minutes

    def __init__(self, app_secret_key: str) -> None:
        self._serializer = URLSafeTimedSerializer(app_secret_key, salt="erp-poc-oauth-state")

    def sign(self, state: str) -> str:
        return self._serializer.dumps({"state": state})

    def unsign(self, cookie_value: str) -> str | None:
        try:
            data = self._serializer.loads(cookie_value, max_age=self._MAX_AGE_SECONDS)
        except (BadSignature, SignatureExpired):
            return None
        return data.get("state")
