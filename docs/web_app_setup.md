# Web app setup

This covers the browser-based app (`erp_poc.web`) specifically. For the
original CLI's setup, see `docs/sandbox_test_procedure.md`. Both share the
same Intuit Developer app and QBO sandbox company — you don't need a
second Intuit app.

## 1. Local database setup

```bash
cd erp-integration-poc
source .venv/bin/activate          # after `pip install -e ".[dev]"` per README
mkdir -p .state
alembic upgrade head                # creates .state/web.db (SQLite, local dev)
```

Local dev uses SQLite (`DATABASE_URL=sqlite:///./.state/web.db` in `.env`).
The hosted deployment uses Postgres instead — same models, same migrations,
different `DATABASE_URL`; nothing else changes.

## 2. Generate the app secrets

```bash
python scripts/generate_secrets.py
```

This prints `APP_SECRET_KEY` (signs session cookies / CSRF tokens) and
prompts for a password, printing `SHARED_PASSWORD_HASH` — the only form
that password is ever stored in. Add both lines to your `.env`:

```
APP_SECRET_KEY=...
SHARED_PASSWORD_HASH=...
DATABASE_URL=sqlite:///./.state/web.db
```

`QBO_CLIENT_ID` / `QBO_CLIENT_SECRET` / `QBO_ENVIRONMENT` are shared with
the CLI's existing `.env` values — no need to duplicate them.

## 3. Register the web app's redirect URI with Intuit

The web app's OAuth callback is `/connection/callback`, not the CLI's
`/callback`. In the Intuit Developer dashboard, on your existing app's
**Redirect URIs**, add (in addition to whatever the CLI already uses):

```
http://localhost:8000/connection/callback
```

Update `.env`'s `QBO_REDIRECT_URI` to match this value for local runs.

## 4. Run it locally

```bash
uvicorn erp_poc.web.asgi:app --app-dir src --reload --port 8000
```

Open http://localhost:8000, log in with the shared password, go to
**QuickBooks connection → Connect QuickBooks**, and complete the browser
consent screen — this is the one step that must happen in an actual
browser; nothing about it can be scripted.

## 5. Hosted redirect URI (after deploying)

Once deployed (see README "Deployment"), the app's callback URL becomes
`https://<your-service>.onrender.com/connection/callback`. Add **that**
URL to the same Intuit app's Redirect URIs list (in addition to, not
instead of, the local one — Intuit allows multiple), and set
`QBO_REDIRECT_URI` in Render's environment variables to match it exactly.
Mismatches here are the most common cause of a failed OAuth callback.

## Notes on the single shared connection

This app supports exactly one active QBO connection at a time, shared by
everyone who logs in (see `REPORT.md` for why). Reconnecting (or a
teammate reconnecting) replaces it. There's no per-user QBO identity —
this mirrors the shared-password model, not a gap introduced separately.
