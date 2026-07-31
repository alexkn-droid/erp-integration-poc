# Deployment (Render)

Step-by-step, with exact pause points marked 🧑 (only you can do this) vs
🤖 (can be done by the AI assistant or you, from the terminal). This
mirrors `docs/sandbox_test_procedure.md`'s format for the CLI.

## 1. Get the code onto GitHub 🧑 (+ 🤖 to push)

1. 🧑 Create a free GitHub account at https://github.com if you don't have
   one.
2. 🧑 Create a new empty repository (no README/license — this repo already
   has one), e.g. `erp-integration-poc`. Copy its URL.
3. 🤖 From the project directory:
   ```bash
   git init
   git add -A
   git commit -m "Initial commit: CLI + web app proof of concept"
   git remote add origin <your-repo-url>
   git branch -M main
   git push -u origin main
   ```
   If `git push` prompts for credentials and hangs in a non-interactive
   shell, run this step yourself in a normal Terminal window instead — it
   only needs your existing GitHub login.

**Before pushing**, double check `.env` and `.state/` are not staged —
`.gitignore` already excludes both, but confirm with `git status` that
nothing named `.env`, `tokens.json`, or `*.db` is about to be committed.

## 2. Create the Render Blueprint 🧑

1. 🧑 Sign up at https://render.com (free).
2. 🧑 Dashboard → **New → Blueprint** → connect your GitHub account → select
   the repo you just pushed.
3. Render reads `render.yaml` and shows a plan: one web service
   (`erp-poc-web`, free) + one Postgres database (`erp-poc-db`, free).
4. 🧑 Render will prompt for the env vars marked `sync: false`:
   - `QBO_CLIENT_ID` / `QBO_CLIENT_SECRET` — from the same Intuit app the
     CLI already uses (Keys & Credentials tab).
   - `QBO_REDIRECT_URI` — leave a placeholder for now (e.g.
     `https://placeholder.onrender.com/connection/callback`); you'll fix
     this in step 4 once the real URL exists.
   - `SHARED_PASSWORD_HASH` — run `python scripts/generate_secrets.py`
     locally first, and paste only the hash (starts with `$pbkdf2-sha256$`)
     here. **Never paste the plaintext password or paste either value into
     a chat with an AI assistant.**
5. 🧑 Click **Apply** / **Deploy**. Render builds and starts the service, and
   provisions Postgres.

## 3. Run migrations 🤖 (automatic)

`render.yaml`'s `startCommand` already runs `alembic upgrade head` before
starting uvicorn on every deploy, so this happens automatically — nothing
extra to do. You can confirm it worked in Render's deploy logs (look for
`Running upgrade -> ..., initial schema`).

## 4. Fix the redirect URI 🧑

1. 🧑 Once deployed, copy the service's real URL from the Render dashboard
   (`https://erp-poc-web-xxxx.onrender.com`).
2. 🧑 In Render's environment variables for `erp-poc-web`, set
   `QBO_REDIRECT_URI` to `https://<that-url>/connection/callback` exactly.
3. 🧑 In the Intuit Developer dashboard, add that same URL to the app's
   Redirect URIs list (keep the existing local ones too).
4. Render redeploys automatically when an env var changes.

## 5. Run the test suite 🤖

Already run locally (79/79 passing) before this deploy — Render doesn't run
the test suite as part of its build by default. If you want CI-style
enforcement later, add a GitHub Actions workflow that runs `pytest -q`;
out of scope for this phase.

## 6. Live sandbox smoke test 🧑 (log in) + 🤖 (drive the rest)

1. 🧑 Open the deployed URL, log in with the shared password.
2. 🧑 **QuickBooks connection → Connect QuickBooks** — this is the one step
   that must happen in your real browser; an AI assistant cannot click
   through Intuit's login screen. Approve access to the sandbox company.
3. From here, either you or the AI assistant (via the now-deployed URL) can
   run through: create a customer, search for it, view it, update it,
   resubmit to confirm duplicate detection, bulk-upload a few test rows,
   create and find a vendor, and confirm everything shows up in Activity
   history.
4. 🧑 Record the outcome in `docs/human_intervention_log.md`.

## Rolling back

Render keeps previous deploys; use **Manual Deploy → Deploy a specific
commit** (or the "Rollback" button on a prior deploy) if a change breaks
something. Database schema changes (new Alembic migrations) are not
automatically reversible — `alembic downgrade` exists but wasn't exercised
in this phase; treat schema rollbacks as a manual, careful operation.
