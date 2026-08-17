# ERP Integration PoC — QuickBooks Online (Customer & Vendor)

Two ways to use this: a **CLI** (original PoC, sandbox-validated) and a
**hosted web app** (built on top of it, for non-technical users). Full
write-up (research, design, evaluation, feasibility) is in
[`REPORT.md`](REPORT.md).

**Status: deployed and live.** The web app is running at
https://erp-poc-web.onrender.com. Both the CLI and the web app have been
run end-to-end against a real QuickBooks Online sandbox company — including
the browser OAuth consent screen itself (Connect QuickBooks → Intuit login
→ redirect back), which needed a human to click through since an AI
assistant can't operate a browser. See `docs/human_intervention_log.md`
for the full, dated record of what was verified, when, and by whom.

## Requirements

- Python 3.12+
- A free Intuit Developer account + sandbox company (human must create this)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run tests (no credentials needed)

```bash
pytest -q
```

Everything runs offline against mocked QBO responses — 85 tests pass as of
this writing. The app has also been deployed and live-tested end to end
against a real QBO sandbox; see `docs/human_intervention_log.md` Session 3
for the full record, including three real bugs found only once a human was
actually driving the deployed app (mocked tests alone didn't catch them).

## Part 1 — CLI

### Human setup (required before any live run)

These steps cannot be done by an AI assistant — they require a human with a
web browser and the authority to create developer accounts:

1. Go to https://developer.intuit.com, sign up for a free Developer account.
2. Create an app → QuickBooks Online → note the **Client ID** and
   **Client Secret** (Development keys).
3. Under the app's Sandbox tab, add a sandbox company if one doesn't exist
   automatically.
4. Add a Redirect URI on the app (e.g. `http://localhost:8000/callback`).
5. Copy `.env.example` to `.env` and fill in `QBO_CLIENT_ID`,
   `QBO_CLIENT_SECRET`, `QBO_REDIRECT_URI`. Leave `QBO_REALM_ID` as a
   placeholder for now — you'll get it in the next step.
6. Follow `docs/sandbox_test_procedure.md` to complete the one-time OAuth
   consent flow and populate the local token cache. This is the only step
   that requires a browser.
7. Update `QBO_REALM_ID` in `.env` with the realm ID from step 6.

**Never paste your Client Secret, access token, or refresh token into a
chat with an AI assistant, a commit message, or a log file.**

### Run against the sandbox (after human setup)

```bash
erp-poc verify-connection
erp-poc create-customer --from-json examples/sample_customer.json
erp-poc read-customer --erp-id <id-from-previous-step> --external-id demo-1
```

`create-customer` will interactively prompt for approval before writing
anything, unless `--yes` is passed. The CLI refuses to run write commands
if `QBO_ENVIRONMENT` is not `sandbox`.

## Part 2 — Web app

A browser UI for the same underlying integration: shared-password login,
create/search/view/update Customers and Vendors, bulk CSV upload,
browser-based QuickBooks connection (no manual OAuth codes), and an
activity history page. No Terminal or local files needed once it's
deployed — see `docs/web_app_setup.md` for full local setup and
`docs/invoice_phase2.md` for why Invoices aren't included yet.

### Quick start (local)

```bash
mkdir -p .state
alembic upgrade head                    # creates the local SQLite DB
python scripts/generate_secrets.py       # prints APP_SECRET_KEY + SHARED_PASSWORD_HASH
# paste both into .env, along with DATABASE_URL=sqlite:///./.state/web.db
uvicorn erp_poc.web.asgi:app --app-dir src --reload --port 8000
```

Open http://localhost:8000, log in, then **QuickBooks connection → Connect
QuickBooks** (see `docs/web_app_setup.md` for the redirect-URI setup this
needs first).

### Deployment (Render)

**Already deployed** at https://erp-poc-web.onrender.com. The steps below
are what it took to get there and are what you'd repeat for a fresh
instance — kept as reference, not a pending to-do.

**Why Render over Railway:** Render has a genuine, permanent free web-service
tier and a managed Postgres with automated backups; Railway no longer offers
a real free tier (a one-time trial credit, then a required payment method)
and its databases are unmanaged containers you'd back up yourself. For a
low-cost internal prototype, Render's simplicity and predictable free tier
win. The one tradeoff: **Render's free Postgres expires after 30 days** and
needs manual re-provisioning — documented here rather than worked around,
per the brief's preference for a real free tier over a paid one for this
phase.

1. Push this repo to GitHub (see `docs/deployment.md` for the exact steps —
   this is a human-required step; an AI assistant cannot create a GitHub
   account or authorize a repo on your behalf).
2. In the Render dashboard: **New → Blueprint**, point it at the repo. Render
   reads `render.yaml` and provisions the web service + Postgres database
   together.
3. Render will prompt for the env vars marked `sync: false` in `render.yaml`
   (`QBO_CLIENT_ID`, `QBO_CLIENT_SECRET`, `SHARED_PASSWORD_HASH`) — enter
   these directly into Render's dashboard, never into a chat with an AI
   assistant. Generate `SHARED_PASSWORD_HASH` locally first with
   `python scripts/generate_secrets.py`.
4. After the first deploy, note the service's URL
   (`https://<name>.onrender.com`), set `QBO_REDIRECT_URI` in Render to
   `https://<name>.onrender.com/connection/callback`, and add that same URL
   to the Intuit app's Redirect URIs list.
5. Redeploy (env var changes trigger this automatically on Render). Log in,
   connect QuickBooks, and run through the smoke test in
   `docs/deployment.md`.

**Gotcha we actually hit:** if you have more than one app registered in the
Intuit Developer dashboard, the redirect URI must be added to the *same*
app whose Client ID/Secret you put in Render — not a different one.
Mismatching them produces a generic "there's a connection problem" error
on Intuit's side that doesn't name the actual cause.

Full step-by-step (including the exact points where Render needs you to
sign in) is in `docs/deployment.md`.

### CSV bulk upload

Upload Customers or Vendors in bulk via CSV — see
[`examples/customers.csv`](examples/customers.csv) and
[`examples/vendors.csv`](examples/vendors.csv) for the expected format.
`display_name` is the only required column; leave `external_id` blank to
have one generated automatically. Limit: 500 rows / 2 MB per file
(configurable via `WebSettings.max_upload_rows` /`.max_upload_bytes`).
`.xlsx` and other spreadsheet formats are rejected, including ones
renamed to `.csv` (checked by content, not just extension).

### Security limitations (read before using this for anything beyond a prototype)

- **Shared password, not accounts.** Anyone with the password has full
  access to every action — no per-user identity, roles, or audit-by-person.
  Appropriate only for a small, trusted internal group testing against a
  disposable sandbox.
- **No secrets-manager integration.** OAuth tokens live in a normal
  Postgres column, not an encrypted secret store. Same trust model as the
  CLI's local token file, just in a shared database now.
- **Single QBO connection, globally shared.** Reconnecting affects
  everyone. Fine for one team testing one sandbox company; wrong for
  anything with more than one "tenant."
- **Free-tier Postgres expires after 30 days** on Render — activity
  history and the customer/vendor ID cache would be lost on
  re-provisioning (QBO itself is unaffected; it's the source of truth).
- **No rate limiting on the app itself** beyond QBO's own — a malicious
  logged-in user could still hammer the API within QBO's limits.
- **Sandbox-only by design**, enforced in code (`require_sandbox_environment`
  in both the web app and the CLI) — not just documentation.

None of these are hard to fix later; they're simply out of scope for an
intern proof of concept, and are called out explicitly so nobody mistakes
this for production-ready.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| "QuickBooks needs to be reconnected" | Refresh token expired (QBO: ~100 days unused) or was revoked. Reconnect via the UI. |
| OAuth callback shows "could not be verified" | The `state` cookie expired (>10 min since clicking Connect) or `QBO_REDIRECT_URI` doesn't exactly match what's registered in the Intuit app. |
| "This action is disabled" (403) on any write | `QBO_ENVIRONMENT` isn't `sandbox`. This is intentional — see Security limitations. |
| CSV upload rejected as "not a plain CSV" | The file is a real spreadsheet format (e.g. `.xlsx`) with a `.csv` extension slapped on — export as CSV from your spreadsheet tool first. |
| Alembic can't connect | `DATABASE_URL` missing/wrong in `.env` (local) or Render env vars (hosted). |

## Project layout

```
src/erp_poc/
  canonical.py       ERP-agnostic data model (CanonicalParty / Customer / Vendor)
  settings.py         CLI env-var configuration (pydantic-settings)
  errors.py            Normalized error hierarchy + QBO fault parsing
  retry.py              Backoff/retry helper
  idempotency.py         Local external_id -> QBO Id map (CLI, file-backed)
  audit.py                 Append-only audit trail (CLI, file-backed)
  qbo_auth.py                OAuth2 token cache + refresh (shared by CLI & web)
  qbo_client.py                Thin QBO Accounting API v3 HTTP client
  transform_qbo.py               QBO Customer/Vendor <-> canonical mapping
  service.py                       Orchestrates create/read/update workflows
  cli.py                             Command-line entry point
  web/
    app.py             FastAPI app factory (create_app) — no import-time side effects
    asgi.py             Production entrypoint: `uvicorn erp_poc.web.asgi:app`
    config.py            WebSettings (separate from the CLI's Settings)
    db.py                 SQLAlchemy engine/session setup
    models_db.py           QboConnection, ActivityLog, ExternalIdMap, BulkUploadJob
    stores.py               DB-backed TokenStore/IdempotencyStore/AuditTrail
    security.py               Password hashing, session cookies, CSRF
    deps.py                     FastAPI dependencies (login/CSRF/sandbox guards)
    party_views.py                Shared Customer/Vendor browser workflow
    csv_import.py                  CSV parsing/validation for bulk upload
    routers/                        auth, dashboard, customers, vendors, bulk, activity, qbo_connection
    templates/, static/               Jinja2 + minimal vanilla CSS
tests/                Unit tests + fully mocked end-to-end tests (CLI + web)
migrations/           Alembic migrations for the web app's database
scripts/
  initial_oauth_exchange.py  One-time, human-run OAuth code exchange (CLI)
  generate_secrets.py         Generates APP_SECRET_KEY + SHARED_PASSWORD_HASH
examples/              Sample CSVs and a sample CanonicalCustomer JSON file
docs/                  Setup, sandbox test procedure, deployment, invoice phase-2 plan
render.yaml            Render Blueprint (web service + managed Postgres)
REPORT.md              Full assignment write-up (all required deliverables)
```
