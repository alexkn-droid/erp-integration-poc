"""Production ASGI entrypoint: `uvicorn erp_poc.web.asgi:app`.

Deliberately separate from app.py's `create_app()` factory: importing
*this* module reads real environment variables and will raise loudly if
they're missing (see WebSettings) — exactly what should happen at
process startup, but NOT what should happen every time a test imports
`erp_poc.web.app` to reach `create_app`.
"""

from __future__ import annotations

from .app import create_app
from .config import get_web_settings

app = create_app(get_web_settings())
