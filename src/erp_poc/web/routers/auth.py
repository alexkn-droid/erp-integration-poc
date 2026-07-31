"""Shared-password login/logout.

There are no user accounts — this is intentional (see README "Security
limitations"). A visitor gets an *unauthenticated* signed session as soon
as they load /login, purely so the login form itself can be CSRF-protected
without a chicken-and-egg problem; on a correct password, that session is
replaced with a fresh, rotated `authenticated=True` one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ..deps import InvalidCsrfToken, get_current_session, get_web_settings, require_login
from ..security import SESSION_COOKIE_NAME, generate_csrf_token, verify_password
from ..templating import render

router = APIRouter()


def _write_cookie(request: Request, response, session: dict) -> None:
    signer = request.app.state.session_signer
    settings = request.app.state.web_settings
    response.set_cookie(
        SESSION_COOKIE_NAME,
        signer.sign(session),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=(request.url.scheme == "https"),
        samesite="lax",
    )


@router.get("/login")
def login_form(request: Request):
    session = get_current_session(request)
    if session and session.get("authenticated"):
        return RedirectResponse(url="/", status_code=303)

    needs_new_cookie = session is None
    if session is None:
        # Issue a pre-auth session purely to CSRF-protect the login form itself.
        session = {"authenticated": False, "csrf_token": generate_csrf_token()}

    response = render(request, "login.html", session=session)
    if needs_new_cookie:
        _write_cookie(request, response, session)
    return response


@router.post("/login")
def login_submit(
    request: Request,
    password: str = Form(...),
    csrf_token: str = Form(...),
    web_settings=Depends(get_web_settings),
):
    session = get_current_session(request)
    if session is None or csrf_token != session.get("csrf_token"):
        raise InvalidCsrfToken()

    if not verify_password(password, web_settings.shared_password_hash):
        response = render(request, "login.html", session=session, status_code=401, error="Incorrect password.")
        return response

    response = RedirectResponse(url="/", status_code=303)
    new_session = {"authenticated": True, "csrf_token": generate_csrf_token()}
    _write_cookie(request, response, new_session)
    return response


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...), session: dict = Depends(require_login)):
    if csrf_token != session.get("csrf_token"):
        raise InvalidCsrfToken()
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
