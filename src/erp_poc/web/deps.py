"""FastAPI dependencies shared across routers.

`require_login` and `require_csrf` raise plain exceptions rather than
HTTPException directly so `app.py` can register exception handlers that
turn them into a friendly redirect (login) or a clear 400 page (CSRF) —
keeping that presentation decision out of every route handler.
"""

from __future__ import annotations

from typing import Iterator, Optional
from urllib.parse import urlencode

from fastapi import Request
from sqlalchemy.orm import Session

from .config import WebSettings
from .security import SESSION_COOKIE_NAME, SessionSigner, csrf_tokens_match


class NotAuthenticated(Exception):
    pass


class InvalidCsrfToken(Exception):
    pass


class NonSandboxWriteBlocked(Exception):
    """Raised if a write is attempted while QBO_ENVIRONMENT != 'sandbox'.

    This app is authorized only for the disposable sandbox company — see
    README "Security limitations." Checked at the point of every write
    (party_views.py, routers/bulk.py), not just at startup, so a
    misconfigured env var can never silently become a production write.
    """


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_web_settings(request: Request) -> WebSettings:
    return request.app.state.web_settings


def get_current_session(request: Request) -> Optional[dict]:
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None
    signer: SessionSigner = request.app.state.session_signer
    return signer.unsign(cookie)


def require_login(request: Request) -> dict:
    session = get_current_session(request)
    if session is None or not session.get("authenticated"):
        raise NotAuthenticated()
    return session


def require_csrf(session: dict, submitted_token: str) -> None:
    if not csrf_tokens_match(submitted_token, session.get("csrf_token", "")):
        raise InvalidCsrfToken()


def require_sandbox_environment(web_settings: WebSettings) -> None:
    if web_settings.qbo_environment != "sandbox":
        raise NonSandboxWriteBlocked()


def redirect_with_message(path: str, message: str, level: str = "success") -> str:
    """Builds a URL carrying a plain-language flash message via query string.

    Simple by design (no server-side flash storage needed) and safe: these
    messages are always short, developer-written, non-sensitive status
    strings — never raw error detail or user-supplied content (base.html
    escapes them regardless, since Jinja autoescapes by default)."""
    return f"{path}?{urlencode({'msg': message, 'level': level})}"
