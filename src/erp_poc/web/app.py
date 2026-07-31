"""FastAPI application factory.

`create_app()` takes an explicit `WebSettings` (and, for tests, an
optional pre-built `engine` and a mocked httpx `transport` for QBO calls)
rather than reading global state, so tests can spin up isolated app
instances pointed at a temp SQLite DB and a scripted QBO transport with
zero monkeypatching.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from ..errors import ERPError
from .config import WebSettings
from .db import make_engine, make_session_factory
from .deps import InvalidCsrfToken, NonSandboxWriteBlocked, NotAuthenticated
from .messages import plain_language_message
from .routers import activity, auth, bulk, customers, dashboard, qbo_connection, vendors
from .security import SessionSigner
from .templating import render

logger = logging.getLogger("erp_poc.web")

STATIC_DIR = Path(__file__).parent / "static"

# A generous global cap; the CSV upload route enforces its own tighter
# settings.max_upload_bytes limit on top of this.
_MAX_BODY_BYTES = 10 * 1024 * 1024


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self._max_bytes:
            return PlainTextResponse("Request too large.", status_code=413)
        return await call_next(request)


def create_app(settings: WebSettings, *, engine=None, qbo_transport=None) -> FastAPI:
    app = FastAPI(title="ERP Integration PoC — QuickBooks Online")

    engine = engine or make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    app.state.web_settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.session_signer = SessionSigner(settings.app_secret_key, max_age_seconds=settings.session_max_age_seconds)
    app.state.qbo_transport = qbo_transport  # None in production; a mocked httpx transport in tests

    app.add_middleware(MaxBodySizeMiddleware, max_bytes=_MAX_BODY_BYTES)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(NotAuthenticated)
    async def _not_authenticated(request: Request, exc: NotAuthenticated):
        return RedirectResponse(url="/login", status_code=303)

    @app.exception_handler(InvalidCsrfToken)
    async def _invalid_csrf(request: Request, exc: InvalidCsrfToken):
        logger.warning("Rejected request with invalid/missing CSRF token: %s %s", request.method, request.url.path)
        return render(
            request,
            "error.html",
            status_code=400,
            title="Request could not be verified",
            message="This form submission could not be verified (invalid or expired security token). Please go back and try again.",
        )

    @app.exception_handler(NonSandboxWriteBlocked)
    async def _non_sandbox_write_blocked(request: Request, exc: NonSandboxWriteBlocked):
        logger.error("Blocked a write attempt while QBO_ENVIRONMENT != 'sandbox': %s %s", request.method, request.url.path)
        return render(
            request,
            "error.html",
            status_code=403,
            title="This action is disabled",
            message="This app is only authorized to write to a QuickBooks sandbox company, and its current configuration is not set to sandbox mode. No data was sent to QuickBooks.",
        )

    @app.exception_handler(ERPError)
    async def _erp_error(request: Request, exc: ERPError):
        logger.warning("ERP error on %s %s [%s]: %s", request.method, request.url.path, type(exc).__name__, exc.message)
        return render(
            request,
            "error.html",
            status_code=502,
            title="QuickBooks request failed",
            message=plain_language_message(exc),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return render(
            request,
            "error.html",
            status_code=500,
            title="Something went wrong",
            message="An unexpected error occurred. It has been logged for the development team.",
        )

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(customers.router)
    app.include_router(vendors.router)
    app.include_router(bulk.router)
    app.include_router(activity.router)
    app.include_router(qbo_connection.router)

    return app
