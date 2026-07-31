# Sandbox integration-test procedure

This procedure has **not been executed** in this session — no QuickBooks
Online account exists yet for this project. It is written so a human
engineer can run it in roughly 15–20 minutes. Steps marked 🧑 must be done
by a human in a browser; steps marked 🤖 can be run by the AI or the human
from the terminal once credentials exist.

## 1. Create developer account and app 🧑

1. https://developer.intuit.com → Sign Up (free).
2. Apps → Create an app → "QuickBooks Online and Payments" → give it a name.
3. On the app's **Keys & credentials** tab (Development), copy the
   **Client ID** and **Client Secret**.
4. On **Redirect URIs**, add `http://localhost:8000/callback` (or whatever
   you'll use — it must match `QBO_REDIRECT_URI` in `.env` exactly).
5. On the **Sandbox** tab, confirm a sandbox company exists (Intuit
   auto-provisions one, seeded with sample data — a fictitious landscaping
   business — the first time you create an app; confirm this in your own
   account rather than assuming, since account provisioning behavior can
   change).

## 2. Configure local environment 🧑

```bash
cp .env.example .env
# edit .env: QBO_CLIENT_ID, QBO_CLIENT_SECRET, QBO_REDIRECT_URI
```

## 3. Complete the OAuth consent flow 🧑

QuickBooks Online uses 3-legged OAuth2 — a human must approve access in a
browser. There is no way to script around this step; it is intentionally
not automated.

1. Build this URL, substituting your Client ID and redirect URI (URL-encode
   the redirect URI):

   ```
   https://appcenter.intuit.com/connect/oauth2
     ?client_id=<QBO_CLIENT_ID>
     &redirect_uri=<url-encoded QBO_REDIRECT_URI>
     &response_type=code
     &scope=com.intuit.quickbooks.accounting
     &state=erp-poc-<random-string>
   ```

2. Open it in a browser, log into the **sandbox** company, click **Connect**.
3. You'll be redirected to your redirect URI with `?code=...&realmId=...&state=...`
   in the query string. Since nothing is listening on that URL yet, the
   browser will show a connection error — that's fine, copy the `code` and
   `realmId` values out of the address bar.
4. Verify the `state` value matches what you sent, to guard against a
   cross-site request forgery on the redirect.

## 4. Exchange the code for tokens 🤖

```bash
python scripts/initial_oauth_exchange.py --code <code> --realm-id <realmId>
```

This writes the token cache (`.state/tokens.json` by default) and never
prints the token values. Update `QBO_REALM_ID` in `.env` to match.

## 5. Verify connectivity 🤖

```bash
erp-poc verify-connection
```

Expected: prints the sandbox company's name and ID. If this fails with an
`ERPAuthError`, redo step 3–4. If it fails with `ERPPermissionError`, the
connected QBO user likely lacks Admin/Accountant rights on that company.

## 6. Create and read back a test customer 🤖 (requires 🧑 approval prompt)

```bash
erp-poc create-customer --from-json examples/sample_customer.json
```

You'll be prompted to confirm the write. Approve it, then confirm the
printed record matches what was sent. Re-run the same command — it should
report `already_exists` rather than creating a duplicate (idempotency
check).

## 7. Negative-path checks 🤖

Run these to exercise the error-handling requirement against the real API,
not just mocks:

- **Duplicate name**: manually create a customer with the same DisplayName
  directly in the QBO sandbox UI, then re-run `create-customer` with a
  *different* `external_id` but the same `display_name` — the local
  idempotency store won't catch it, so it must fall through to the live
  DisplayName query.
- **Invalid token**: temporarily corrupt `.state/tokens.json` (e.g. edit the
  `access_token` field) — confirm the client attempts a refresh, and that a
  bad refresh token produces a clear `ERPAuthError` telling the human to
  re-authorize, not a stack trace.
- **Malformed input**: run `create-customer` against a JSON file missing
  `display_name` — confirm it's rejected by Pydantic validation before any
  network call is made.
- **Rate limit**: not practical to trigger deliberately in a low-volume
  sandbox test; covered by the mocked test suite instead
  (`test_transient_429_on_create_is_retried_then_succeeds`).

## 8. Record results

Append actual outcomes (pass/fail, any deviations from the above) to
`docs/human_intervention_log.md` under a new dated entry once this
procedure is actually run.
