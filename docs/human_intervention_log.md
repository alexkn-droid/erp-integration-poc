# Human decision & intervention log

This is a running record of every point in this proof of concept where a
human decision, credential, or approval was required — not a hypothetical
list, but what actually happened while building this PoC. New entries
should be appended (dated) as the sandbox procedure is actually run.

## Session 1 — 2026-07-28: Research, design, and implementation

| # | Decision / action | Who | Notes |
|---|---|---|---|
| 1 | Choose QuickBooks Online over NetSuite as the PoC ERP | AI, autonomous | Within the mandate given ("recommend one ERP and explain why"); grounded in verified accessibility research. A human should still sign off before any resources are spent acting on it — see REPORT.md Assumptions. |
| 2 | Choose Customer create+read-back as the workflow | AI, autonomous | Same rationale — explicitly an "AI can perform independently" task (proposing schemas/mappings, drafting design). |
| 3 | Field mapping choices (which QBO fields map to which canonical fields) | AI, autonomous, **needs human review** | This is explicitly listed in the spec as "AI can perform with human approval." No human has reviewed `transform_qbo.py` yet. Flagging here rather than silently treating it as final. |
| 4 | Create Intuit Developer account | **Human required** | Not done. AI cannot create third-party accounts or accept Intuit's terms of service on anyone's behalf. |
| 5 | Obtain Client ID / Client Secret | **Human required** | Not done. Secrets must never be typed into a chat with an AI assistant — the `.env` file is local-only and gitignored. |
| 6 | Complete OAuth2 browser consent (authorize the app against a real sandbox company) | **Human required** | Not done — genuinely cannot be automated; QBO's 3-legged OAuth requires an interactive login. See `docs/sandbox_test_procedure.md` step 3. |
| 7 | Approve the first live write (`create-customer`) against the sandbox | **Human required, per-write** | Not yet reached. The CLI hard-codes an interactive confirmation prompt for exactly this reason (`cli.py`, `approve()` callback), and refuses to run write commands unless `QBO_ENVIRONMENT=sandbox`. |
| 8 | Validate that generated code is correct | AI wrote it and ran the test suite (34/34 passing, mocked only) | **Needs human code review** before being trusted with real data — this is unverified against a live API and a human engineer should read `service.py` and `qbo_client.py` specifically, since those own retry/idempotency/write-safety behavior. |
| 9 | Confirm exact QBO request/response field names and limits against live interactive API docs | **Needs human verification** | The AI could not render developer.intuit.com's JS-based doc explorer through automated tools in this session; mappings are based on secondary sources (see REPORT.md Phase 3 citations) and general knowledge of the QBO API, not a fetch of the primary schema reference. Flagged explicitly rather than presented as verified. |

## Session 2 — 2026-07-31: Web app, generalized to Customer + Vendor, live-tested

Between session 1 and this one, a human completed items 4–7 below on their
own initiative: created the Intuit Developer account, obtained real
credentials, ran the browser OAuth consent flow, and used the CLI to
create a real sandbox customer (`.state/audit.log` shows `sync_customer`
→ `erp_id: 58`, 2026-07-29) — evidence this session confirmed by reading
that log, not by assuming it. This corrected an earlier back-and-forth in
this session where the AI initially (and wrongly) told the user no live
validation had occurred; the audit log settled it.

| # | Decision / action | Who | Notes |
|---|---|---|---|
| 10 | Generalize `CanonicalCustomer`/`transform_qbo`/`service.py` into shared Customer+Vendor abstractions | AI, autonomous | Reused the existing, already-approved Customer design rather than inventing a new one for Vendor — kept all 34 original CLI tests passing unmodified as the safety check. |
| 11 | Choose Render over Railway for hosting | AI, autonomous, **explained in README/REPORT** | Explicitly delegated to the AI in the assignment ("determine whether Render or Railway is a better fit... explain the choice briefly"); grounded in the same day's pricing/feature research, not assumed from training data. |
| 12 | Accept Render's free-tier Postgres 30-day expiry vs. paying ~$7/mo for persistence | **Human decision** | Asked directly rather than assumed; human chose the free tier and accepted the documented limitation. |
| 13 | Confirm no GitHub account exists yet for pushing this repo | **Human confirmed** | Asked directly; human does not yet have one. Deployment (docs/deployment.md) is written but not yet executed — GitHub account creation is the next human-required step. |
| 14 | Live-test the web app's Customer/Vendor/bulk-upload workflows against the real sandbox | AI, with a shortcut disclosed here | The AI seeded the web app's database directly from the CLI's already-authorized refresh token (`.state/tokens.json`) rather than performing the browser OAuth consent itself — because it genuinely cannot click through Intuit's login screen. This let create/search/view/update/duplicate-detection/bulk-upload all be proven against the real API (new sandbox records: customers 59–61, 63–64, vendor 62), but the **browser OAuth round-trip itself (Connect QuickBooks button → Intuit login → redirect back) remains unverified** — flagged, not glossed over. |
| 15 | Vendor field-mapping assumption (Customer-identical shape) | **Confirmed live**, not just assumed | Session 1's REPORT.md flagged NetSuite/Vendor mapping details as unverified secondary-source claims. This session's live vendor create (QBO ID 62) confirms the QBO Vendor entity does in fact mirror Customer's field shape — upgrading that from "assumed" to "confirmed." |
| 16 | Sandbox-only write enforcement for the web app | AI caught its own gap | The CLI has always refused writes outside `QBO_ENVIRONMENT=sandbox`; the AI initially built the web app *without* the equivalent guard, caught it before writing tests, and added `require_sandbox_environment` (enforced at every write route, tested in `tests/web/test_customers.py` and `test_bulk_upload.py`). Noting the miss, not just the fix. |

## Session 3 — 2026-08-03 to 2026-08-17: Deployment and live smoke test

The human created a GitHub account and a Render account (both genuinely
required — the AI cannot create third-party accounts), pushed the repo,
and drove the entire deployment through Render's Blueprint flow, entering
all secrets directly into Render's dashboard rather than sharing them in
chat. The AI diagnosed and fixed three real bugs found only because a real
human clicked through the actual deployed site — none of these surfaced in
the 85 automated tests, which is itself a useful data point about the
limits of mocked-API testing.

| # | Decision / action | Who | Notes |
|---|---|---|---|
| 17 | Create GitHub + Render accounts, push the repo, complete Render's Blueprint setup | **Human required, done** | Including recovering a forgotten Render password and a forgotten app shared-password — both handled by the human via each service's own recovery/reset flow, not by the AI. |
| 18 | Fix: `DATABASE_URL` scheme mismatch (`postgres://` vs the `psycopg` v3 driver's required `postgresql+psycopg://`) | AI, autonomous — caught from a Render deploy log the human pasted | This is exactly the kind of environment-specific failure that never shows up in local SQLite-backed tests; only surfaced once actually deployed against Render's Postgres. |
| 19 | Fix: `/login` page incorrectly showed the authenticated nav bar + working Logout button to logged-out visitors | AI, self-caught by inspecting the live page's HTML, not reported by the human | `bool(session)` was true even for the pre-auth, `authenticated: False` session `/login` issues to CSRF-protect its own form. Added a regression test. |
| 20 | Complete the actual browser "Connect QuickBooks" OAuth click-through | **Human required, done** | The one step flagged in session 2 as never verified by a real browser. Required a real fix along the way (item 21) before it worked. |
| 21 | Fix: OAuth redirect_uri registered on the wrong Intuit app | Human diagnosed with AI guidance, human fixed in Intuit's dashboard | The human has multiple Intuit apps; Render's `QBO_CLIENT_ID`/`SECRET` pointed at a different one ("ERP Test") than the one with the redirect URI registered. Diagnosed by comparing the `client_id` in the actual failing OAuth URL against `.env` — the AI compared them programmatically without printing either value into chat. |
| 22 | Fix: strict email format validation crashed the live Vendors page | AI, autonomous, from a Render log traceback the human pasted | QBO's own seeded sandbox sample data has a Vendor with two comma-separated addresses in one email field — valid to QBO, rejected by our `EmailStr` field. This was flagged as an *open, undecided question* in session 2's log; a real production-like crash resolved it in favor of matching QBO's own leniency. Directly analogous to the "documentation gaps" the original REPORT.md Phase 3 flagged — QBO's actual data behavior kept being looser than assumed. |
| 23 | Full manual smoke test on the live deployed app (login, connect, customer CRUD, vendor create, activity history, bulk CSV upload) | Human executed, AI guided step by step and diagnosed each failure | All steps eventually passed; two of the CSV upload's apparent "failures" during testing turned out to be a malformed test fixture file the AI itself had generated (an off-by-one missing CSV column), not an app bug — worth noting as a reminder that test data errors can look identical to product bugs from the outside. |

## Open items requiring a human

- [x] Create Intuit Developer account + sandbox company (item 4) — done 2026-07-29 or earlier
- [x] Populate `.env` with real Client ID/Secret (item 5) — done
- [x] Run the CLI's OAuth consent flow (item 6) — done
- [x] Execute a live create against the sandbox — done via CLI (2026-07-29) and via the web app (2026-07-31)
- [x] **Complete the browser OAuth consent flow through the actual "Connect QuickBooks" button** — done 2026-08-11, after fixing item 21 above
- [x] Create a GitHub account (item 13) and push this repo — done
- [x] Create a Render account and complete the Blueprint deploy — done; live at the URL in README.md
- [x] Full manual smoke test on the deployed app — done 2026-08-17, all steps passing
- [ ] Review `transform_qbo.py` field mappings against the live API reference (Customer and Vendor both confirmed live; still worth a pass against the primary docs for edge cases like multi-currency)
- [ ] Confirm the shared sandbox company has at least one QBO Item before scoping invoice work (`docs/invoice_phase2.md`)
- [ ] Consider revoking/rotating the GitHub personal access token used during setup — it was typed into a local Terminal several times over the course of deployment; never committed or shared in chat, but rotating it is good hygiene given how much handling it got
- [ ] Decide on a longer-term secret-storage story before this app handles anything beyond disposable sandbox data (see README "Security limitations" — tokens are still stored as plain database columns)

## Template for future entries

```
## Session N — <date>: <short description>
| # | Decision / action | Who | Notes |
```
