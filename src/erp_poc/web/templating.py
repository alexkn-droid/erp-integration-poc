"""Single Jinja2 rendering helper so every route builds template context the same way."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def render(
    request: Request,
    template_name: str,
    *,
    session: Optional[dict] = None,
    status_code: int = 200,
    **context,
):
    ctx = {
        "csrf_token": (session or {}).get("csrf_token", ""),
        "logged_in": bool(session),
        "flash_message": request.query_params.get("msg"),
        "flash_level": request.query_params.get("level", "success"),
        **context,
    }
    # Starlette's TemplateResponse signature is (request, name, context, ...) —
    # `request` first, not `name` first (that was the pre-1.0 signature).
    return templates.TemplateResponse(request, template_name, ctx, status_code=status_code)
