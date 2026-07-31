"""Browser-based QuickBooks OAuth connection management.

Replaces the CLI's manual "copy the code out of the browser and run a
script" flow (scripts/initial_oauth_exchange.py) with a real redirect
round-trip: /connection/start sends the browser to Intuit,
/connection/callback receives it back and finishes the exchange
automatically using the same `qbo_auth.exchange_code_for_tokens` /
`get_valid_access_token` functions the CLI already uses.

Only one connection is supported at a time (DbTokenStore.save_new_connection
replaces any existing row) — matching the "single shared sandbox company"
requirement.
"""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ... import qbo_auth
from ...errors import ERPError
from ..deps import InvalidCsrfToken, get_db, require_csrf, require_login
from ..qbo import get_connection_status, get_qbo_client_or_none
from ..security import OAUTH_STATE_COOKIE_NAME, OAuthStateSigner
from ..templating import render

logger = logging.getLogger("erp_poc.web")

router = APIRouter(prefix="/connection")

_CONSENT_URL = "https://appcenter.intuit.com/connect/oauth2"
_SCOPE = "com.intuit.quickbooks.accounting"


@router.get("")
def connection_status_page(request: Request, db: Session = Depends(get_db), session: dict = Depends(require_login)):
    status = get_connection_status(db)
    health = None
    if status.connected:
        client = get_qbo_client_or_none(request, db)
        try:
            info = client.verify_connection()
            health = {"ok": True, "company_name": info.get("CompanyName")}
        except ERPError as exc:
            health = {"ok": False, "message": str(exc.message)}
        finally:
            client.close()
    return render(request, "connection.html", session=session, status=status, health=health)


@router.get("/start")
def connection_start(request: Request, session: dict = Depends(require_login)):
    web_settings = request.app.state.web_settings
    state = secrets.token_urlsafe(24)

    params = {
        "client_id": web_settings.qbo_client_id,
        "redirect_uri": web_settings.qbo_redirect_uri,
        "response_type": "code",
        "scope": _SCOPE,
        "state": state,
    }
    response = RedirectResponse(url=f"{_CONSENT_URL}?{urlencode(params)}", status_code=303)

    state_signer = OAuthStateSigner(web_settings.app_secret_key)
    response.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        state_signer.sign(state),
        max_age=600,
        httponly=True,
        secure=(request.url.scheme == "https"),
        samesite="lax",
    )
    return response


@router.get("/callback")
def connection_callback(
    request: Request,
    code: str | None = None,
    realmId: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    """Deliberately NOT behind require_login (per spec: "protect every page
    except login and OAuth callback") — state validation against the
    signed, short-lived cookie set in /connection/start is what protects
    this route instead."""
    web_settings = request.app.state.web_settings
    state_cookie = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    state_signer = OAuthStateSigner(web_settings.app_secret_key)
    expected_state = state_signer.unsign(state_cookie) if state_cookie else None

    if not code or not realmId or not state or not expected_state or state != expected_state:
        logger.warning("OAuth callback rejected: missing/mismatched state")
        response = render(
            request,
            "error.html",
            status_code=400,
            title="QuickBooks connection failed",
            message="The connection attempt could not be verified (missing or expired state). Please try Connect QuickBooks again.",
        )
        response.delete_cookie(OAUTH_STATE_COOKIE_NAME)
        return response

    tokens = qbo_auth.exchange_code_for_tokens(web_settings, authorization_code=code)

    from ..stores import DbTokenStore

    token_store = DbTokenStore(db)
    token_store.save_new_connection(realm_id=realmId, company_name=None, tokens=tokens)

    from ...qbo_client import QBOClient

    client = QBOClient(web_settings, token_store, realm_id=realmId, transport=getattr(request.app.state, "qbo_transport", None))
    try:
        info = client.verify_connection()
        connection = token_store.current_connection()
        if connection is not None:
            connection.company_name = info.get("CompanyName")
            db.commit()
    except ERPError:
        logger.warning("Connected, but CompanyInfo lookup failed immediately after connecting", exc_info=True)
    finally:
        client.close()

    response = RedirectResponse(
        url="/connection?" + urlencode({"msg": "QuickBooks connected successfully.", "level": "success"}),
        status_code=303,
    )
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME)
    return response


@router.post("/disconnect")
def connection_disconnect(
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    session: dict = Depends(require_login),
):
    require_csrf(session, csrf_token)
    from ..stores import DbTokenStore

    DbTokenStore(db).disconnect()
    return RedirectResponse(
        url="/connection?" + urlencode({"msg": "QuickBooks disconnected.", "level": "warning"}),
        status_code=303,
    )
