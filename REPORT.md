# AI-Assisted ERP Integration — Proof of Concept Report

**Central question:** Can an advanced AI model, working with a human engineer,
materially accelerate the process of building a reliable integration with one
ERP from its API documentation?

**Scope tested:** authenticate → read a real object → transform to a
canonical model → create a test object → read it back → validate → handle
several expected error conditions, with explicit human checkpoints
throughout.

---

## 0. Session 2 update — web application (2026-07-31)

Everything below section 0 is the original session-1 report, unmodified.
This section records what changed since: the CLI became a browser-based
internal tool, extended from Customer-only to Customer + Vendor, with bulk
CSV upload, a database-backed activity history, and a browser OAuth
connection flow. Full detail: `README.md` (setup/deployment),
`docs/human_intervention_log.md` Session 2 (every decision and its
rationale), `docs/invoice_phase2.md` (deferred work), `docs/deployment.md`.

**Previously completed (session 1, CLI):** authenticate, read, transform,
create, read-back, and error-handling, all against a real QBO sandbox
company — confirmed via `.state/audit.log` (a real `sync_customer` create,
QBO ID 58, dated 2026-07-29), not just the mocked tests session 1 shipped
with. This corrects session 1's own report, which — accurately, at the
time it was written — could not yet claim live validation.

**Newly completed (session 2, web interface):** a FastAPI + server-rendered
web app reusing the CLI's `qbo_client`/`qbo_auth`/error/retry layers
unchanged, generalizing the Customer-only canonical model and sync service
into shared Customer+Vendor abstractions (`CanonicalParty`,
`PartySyncService`) with zero changes to existing CLI behavior (all 34
original tests still pass, unmodified). Added: shared-password auth with
signed sessions and CSRF protection, a two-step review-and-confirm write
flow, bulk CSV upload (validate → preview → confirm → process → downloadable
results), a database-backed activity history, and a browser-based
QuickBooks connection flow (replacing the CLI's manual
copy-the-code-out-of-the-browser step). 79 automated tests (34 CLI + 45
web), all passing, all offline against mocked QBO responses.

**Deployed sandbox validation — partially done, honestly:** the web app was
run locally end-to-end against the **real** QBO sandbox (not mocks) —
customer create/search/view/update/duplicate-detection, vendor create,
and bulk upload (2 rows created, 1 correctly rejected while processing
continued) all genuinely happened against QuickBooks, creating real sandbox
records (customer IDs 59–61, 63–64; vendor ID 62). This also newly
*confirmed* a claim session 1 had flagged as unverified: QBO's Vendor
entity does mirror Customer's field shape. What's **not yet done**: hosted
deployment to Render, and — this matters — the actual browser click-through
of "Connect QuickBooks → Intuit login → redirect back." The AI seeded the
local database directly from the CLI's already-authorized token rather than
performing that OAuth handshake, because it cannot operate a browser.
That one interactive step is the first thing a human should verify, either
locally or after deployment (`docs/deployment.md`'s smoke test covers it).
**Update: both of these are now done — see section 0b below.**

**Remaining invoice work:** deliberately deferred, not attempted. Invoices
are a structurally different problem (nested line items, product/service
selection, tax) that doesn't fit the Customer/Vendor abstraction without
new code, and the brief explicitly permitted deferring rather than risking
the working system. Full assessment and effort estimate:
`docs/invoice_phase2.md`.

**Limitations before any production use:** see README "Security
limitations" for the full list (shared password with no per-user identity,
tokens stored unencrypted in the database, single globally-shared QBO
connection, free-tier Postgres' 30-day expiry, sandbox-only enforcement).
None are hard to address later; all are out of scope for an intern PoC and
called out explicitly rather than silently accepted.

## 0b. Session 3 update — deployment and live smoke test (2026-08-03 to 2026-08-17)

**Deployed sandbox validation — now fully done.** The app is live at the
hosted URL in `README.md`, backed by a real Render Postgres database. A
human completed every step that genuinely required a human — GitHub and
Render account creation, entering secrets directly into Render's dashboard
(never into chat), and the actual browser click-through of "Connect
QuickBooks" against the real Intuit login/consent screen. That last step
is the one piece of the whole project that could not have been verified by
the AI alone, no matter how much of the rest it automated — a concrete,
literal answer to "what does a human still have to do."

**Three real bugs were found this session, all only visible once a human
was actually driving the deployed app** — none had shown up in the 85
automated (mocked) tests:

1. **Database driver mismatch**: Render's Postgres connection string uses
   `postgres://`, but the installed driver (`psycopg` v3) needs
   `postgresql+psycopg://` explicitly — this crashed `alembic upgrade
   head`, the very first thing the app's start command runs, before it
   ever bound a port. Fixed by normalizing the URL in code, at both the
   app's own engine and Alembic's migration runner.
2. **Login page UI bug**: `bool(session)` was used as a proxy for "is this
   user logged in," but the *unauthenticated* session `/login` creates
   purely to CSRF-protect its own form is a non-empty dict — also
   truthy. Logged-out visitors briefly saw the full authenticated nav bar
   and a working Logout button on the login page itself.
3. **Data-shape assumption broken by real data**: strict RFC email
   validation (`EmailStr`) crashed the entire Vendors list page once it
   hit a real seeded QBO sandbox record with two comma-separated
   addresses in one email field — valid to QBO, invalid to our stricter
   rule. This had been logged as an open, undecided question in session
   2's `docs/human_intervention_log.md`; a live crash settled it in favor
   of matching QBO's own (looser) behavior rather than an idealized spec
   of it.

None of these were hypothetical risks flagged in the abstract — each was
found from an actual Render deploy log or an actual broken page a human
was looking at, then fixed and re-verified live. This is arguably the most
concrete evidence in this whole report for the central question: the AI
could diagnose and fix each one from a pasted log/error in minutes, but
**could not have found any of them without a human actually operating the
deployed system** — the two are complementary, not substitutes for each
other.

Full smoke test executed and passing on the live deployed app: login →
QuickBooks connection (real OAuth) → customer create/search/view/update →
duplicate detection → vendor create → activity history → bulk CSV upload
(mixed valid/invalid rows, processed correctly). See
`docs/human_intervention_log.md` Session 3 for the complete, dated record.

---

## 1. Executive summary

**What was tested.** Whether an AI working from public documentation (via
live web research, not just training knowledge) can select an appropriate
ERP, design a mapping and architecture, and produce a working, tested
integration codebase with materially less manual engineering than a
from-scratch build — while being honest about what still requires a human.

**ERP selected: QuickBooks Online (QBO)**, not NetSuite. NetSuite was the
assignment's default candidate, but research (Section 3) found no
self-service way to obtain a free NetSuite sandbox: every path requires
contacting sales or requesting SDN approval and waiting on NetSuite's team,
with no published SLA. QuickBooks Online offers an instant, free,
self-service developer account and sandbox company at
[developer.intuit.com](https://developer.intuit.com), a well-documented REST
API, and OAuth2 auth — a materially better fit for "low-cost, accessible,
technically meaningful proof of concept," which the assignment explicitly
permits as grounds for deviating from NetSuite. QBO is accounting software
rather than a full ERP suite, which is a real scope limitation, noted in
Section 2.

**Workflow selected: Customer master-data sync** — read an existing
customer, create a new one from a canonical record (idempotently), read it
back, and validate. Ranked #1 of three candidates (Section "Workflow
ranking") on the assignment's own criteria: lowest security risk, lowest
dependency on account-specific configuration, highest testability.

**Feasibility: feasible with specific prerequisites.** The full codebase —
canonical model, transform layer, HTTP client, OAuth handling, retry/backoff,
idempotency, audit trail, CLI, and 34 passing tests (unit + fully mocked
end-to-end) — was built and is included in this repository. It has **not**
been run against a live QBO sandbox in this session, because doing so
requires a human to create an Intuit Developer account and complete a
browser-based OAuth consent step — that is a hard technical boundary, not a
shortcut taken. See Section 8 for the full feasibility argument.

**Most important limitation.** Everything about request/response field
shapes, error codes, and rate limits in this report is sourced from QBO's
official docs *indirectly* — through secondary technical write-ups and
general knowledge — because `developer.intuit.com`'s interactive API
reference is a JavaScript application that automated fetching could not
render in this session (Section 3 flags every claim that needs live
verification). Nothing here has been confirmed against a real API response.

**Recommended next step.** A human engineer spends ~20 minutes following
`docs/sandbox_test_procedure.md`: create the free Intuit developer account,
complete the OAuth consent flow, and run the CLI against the real sandbox.
That single session will confirm or correct every mapping and error-handling
assumption in this report and convert "feasible with prerequisites" into
either "feasible now" or a short, concrete punch list.

---

## 2. Assumptions and open questions

These materially affect the result if wrong. None of them were silently
resolved — they're listed so a human can confirm or override them.

| # | Assumption | Why it matters | If wrong |
|---|---|---|---|
| A1 | A QBO sandbox company, not a paid production company, is an acceptable stand-in for "one ERP" for this PoC, even though QBO is SMB accounting software rather than a full multi-entity ERP like NetSuite/SAP. | The assignment's business context is about connecting to "systems of record, particularly ERP platforms" generally, and explicitly allows substituting a more accessible platform. But if the eventual commercial target is specifically large enterprise NetSuite/SAP customers, QBO's data model (no subsidiaries, simpler chart-of-accounts, no advanced revenue recognition) under-represents that complexity. | Re-run Phase 1–2 against NetSuite once sandbox access is actually secured (see Section 3), budgeting for its longer approval timeline. |
| A2 | "Customer" master data (not Invoice, Vendor, or Payment) is the right first workflow. | Chosen for lowest risk/config-dependency per the assignment's own ranking criteria (Section "Workflow ranking"). | If the real business driver is specifically AP (vendor bills) or AR (invoicing) automation, Vendor or Invoice should be built next — the architecture is designed so that's additive, not a rewrite (Section 9). |
| A3 | A flat local JSON file is an acceptable idempotency store and token cache for a PoC. | Explicitly not production-grade — no encryption at rest, no concurrent-writer safety. | Before any production use: token cache → secrets manager (AWS Secrets Manager/Vault); idempotency store → a real database table with a unique constraint. |
| A4 | Field-level limits (e.g., DisplayName max length, which fields are truly required by QBO vs. only recommended) are approximated from secondary sources, not confirmed against the live schema. | Wrong limits either reject valid data or accept data QBO will reject, surfacing as a confusing runtime error instead of a clean validation error. | Must be confirmed in the first live sandbox test run (docs/sandbox_test_procedure.md, step 7). |
| A5 | No custom fields, multi-currency edge cases, or company-specific configuration exist in the target QBO company. | Custom fields and multi-currency add validation and mapping complexity not modeled here. | Would need to extend `canonical.py` / `transform_qbo.py` once real account configuration is known — flagged as a gap, not solved. |
| A6 | "Human must perform" boundaries (account creation, OAuth consent, per-write approval) match what this specific organization's security policy actually requires. | The PoC assumes the stated policy from the assignment; a real org might require additional approvals (e.g., security review sign-off before any sandbox write). | Confirm with the org's actual access-control policy before treating this PoC's checkpoints as sufficient for production rollout. |

**Not assumed / explicitly out of scope:** production credentials, webhooks,
multi-tenant/multi-company support, update or delete operations, and any
object other than Customer. These are named directly rather than silently
build-then-omitted.

---

## 3. ERP-access assessment

### 3.1 Comparison: NetSuite vs. QuickBooks Online vs. Xero

| Criterion | NetSuite | QuickBooks Online | Xero |
|---|---|---|---|
| Self-service free sandbox | **No** — confirmed. No public self-service signup; the standard path is a free trial *account* followed by a separate "Request Access" application to the SuiteCloud Developer Network (SDN), reviewed and approved by NetSuite's team on an unstated timeline. [Process.st](https://www.process.st/how-to/get-a-netsuite-developer-account/), [Folio3](https://netsuite.folio3.com/blog/what-is-netsuite-developer-account-a-complete-guide/) | **Yes** — confirmed. Sign up at [developer.intuit.com](https://developer.intuit.com), sandbox company available immediately, free. [Satva Solutions](https://satvasolutions.com/blog/quickbooks-online-app-using-intuit-developer-portal) | **Yes**, with caveats — confirmed. A demo company is available for new test apps, but the demo company resets periodically and record IDs are not guaranteed to persist; a 30-day trial org is the alternative for persistent testing. [Xero Developer FAQ](https://developer.xero.com/faq/getting-started), [Xero dev accounts docs](https://developer.xero.com/documentation/development-accounts/) |
| Cost | SDN has a genuinely free tier for individual/technical-only access, per NetSuite's own marketing page — but "free" doesn't mean fast or guaranteed (see below). Paid Select/Premier tiers exist for go-to-market partners, not needed here. | $0. | $0 for demo/trial; production API access requires an approved app if you exceed trial limits. |
| Time to first API call | **Unconfirmed, likely days** — approval-gated, no published SLA. One source described contacting a sales rep or Solution Provider as the standard path for a developer account. | **Confirmed: minutes.** Account → app → sandbox company → OAuth in one sitting. | Confirmed: minutes for the demo company; the 28-day-expiring nature adds re-setup friction for anything beyond a single session. |
| API completeness for this use case (Customer CRUD) | Full (REST + SOAP SuiteTalk, SuiteScript). | Full (Accounting API v3 covers Customer create/read/update/query). | Full (Accounting API covers Contacts, Xero's equivalent of Customer/Vendor). |
| Auth complexity | OAuth 2.0 (Client Credentials, machine-to-machine) or legacy Token-Based Auth — comparatively simpler than QBO's 3-legged flow because it doesn't require a browser consent step. [Modern Treasury](https://www.moderntreasury.com/journal/how-to-authenticate-to-netsuites-suitetalk-rest-web-services-api) | OAuth 2.0 Authorization Code (3-legged) — requires an interactive browser consent per company connection; 1-hour access tokens, 100-day rolling, single-use rotating refresh tokens. | OAuth 2.0 Authorization Code, broadly similar shape to QBO. |
| Rate limits | Not independently confirmed in this session; commonly documented as account-tier-dependent concurrency limits (not verified here — flagged). | **Confirmed (secondary source): 500 requests/minute per realm, 40 concurrent requests.** [Satva Solutions QBO API guide](https://satvasolutions.com/blog/quickbooks-online-api-guide) | Not independently confirmed in this session. |
| Relevance to eventual commercial use case | Highest — NetSuite is a named target platform in the business context and is the more common system of record among the larger customers this integration approach would eventually need to support. | Lower — QBO is SMB-tier, not full ERP; a real NetSuite connector would still need to be built separately later. | Similar tier to QBO; slightly less common in the US mid-market than QBO. |

**Recommendation: QuickBooks Online for this proof of concept.** The
assignment explicitly authorizes deviating from NetSuite "if NetSuite
sandbox access is unavailable or impractical" — and self-service, same-day
access is unavailable for NetSuite as confirmed above. QBO lets the *actual
question this PoC is testing* (can AI accelerate ERP integration
development?) get tested this session rather than blocked for days on an
approval queue. The cost of this choice is that QBO's data model is simpler
than NetSuite's; Section 9 estimates what changes for a NetSuite connector
specifically so that gap is not hidden.

**How the NetSuite version would differ**, for when sandbox access is later
obtained:
- Auth: OAuth 2.0 Client Credentials (machine-to-machine, no browser step) or
  Token-Based Auth, replacing `qbo_auth.py`'s 3-legged flow — likely
  *simpler* to automate, ironically, once access exists.
- Base URL / record model: `https://{account_id}.suitetalk.api.netsuite.com/services/rest/record/v1/{record_type}`
  instead of QBO's `/v3/company/{realmId}/{entity}` — a different
  `qbo_client.py`-equivalent, same shape.
- Data model: NetSuite's Customer record carries substantially more
  subsidiary/multi-book-accounting fields; the canonical model would likely
  need an optional `subsidiary_id`-style extension field.
- Idempotency: NetSuite's REST API has its own duplicate-detection behavior
  that would need separate confirmation (not researched in this session —
  flagged as a gap, not assumed).

### 3.2 What a human must do to get a working test environment (QBO)

1. Create a free account at developer.intuit.com (accept Intuit's terms — an
   AI cannot do this).
2. Create an app, obtain Client ID/Secret (a secret — never share with an
   AI assistant).
3. Confirm/create a sandbox company under that app.
4. Complete a one-time browser OAuth consent (cannot be scripted).

No cost, no sales call, no approval wait — this is the concrete accessibility
advantage over NetSuite. Full steps: `docs/sandbox_test_procedure.md`.

---

## 4. Technical design

### 4.1 Workflow ranking (Phase 2)

Three candidate workflows were scored against the assignment's six criteria
(business value, implementation difficulty, testability, security risk,
config-dependency, scaling evidence — lower risk/difficulty/dependency is
better, higher value/testability/scaling-evidence is better):

| Workflow | Business value | Difficulty | Testability | Security risk | Config dependency | Scaling evidence | Rank |
|---|---|---|---|---|---|---|---|
| **Customer** create + read-back | Medium — master-data sync is the near-universal first step of any ERP integration | Low | High — no prerequisite records needed | Low — no monetary amount, easily deleted/deactivated in sandbox | Low — works in a bare sandbox company | Medium — flat object, doesn't exercise nested-line-item mapping | **1** |
| **Vendor** create + read-back | Medium — mirrors Customer on the AP side | Low | High | Low | Low | Low — nearly identical to Customer technically, adds little new evidence | 3 |
| **Invoice** create + read-back | High — revenue documents are usually the highest-value integration target | Medium-High — requires a valid `CustomerRef` and line items referencing an `Item`/account | Medium — depends on sandbox having a pre-seeded Customer/Item (commonly true for QBO's auto-provisioned sample company, but not independently confirmed) | Medium — a financial document, even if voidable in sandbox | Higher — depends on chart-of-accounts/items already existing | High — exercises nested objects, references, more realistic of the actual integration difficulty a customer-facing product would face | 2 |

**Selected: Customer create + read-back.** It best satisfies the
assignment's explicit preference ("prefer a low-risk object such as a
customer, vendor, or test invoice") while maximizing testability and
minimizing setup fragility for a same-session PoC. Invoice is the natural
"workflow #2" once a live sandbox is confirmed working — flagged in Section
9 rather than attempted here, since taking on its extra config-dependency
risk wasn't justified for proving the core AI-acceleration question.

### 4.2 Canonical schema and field mapping

`CanonicalCustomer` (`src/erp_poc/canonical.py`):

| Canonical field | Required | QBO field | Notes / source |
|---|---|---|---|
| `external_id` | Yes | *(none — our system's key, used only for the local idempotency map)* | Not a QBO field. |
| `display_name` | Yes | `DisplayName` | QBO's only strictly required field for Customer create, per multiple secondary sources; **not independently confirmed against the live schema** — flagged in Section 2 (A4). |
| `company_name` | No | `CompanyName` | |
| `email` | No | `PrimaryEmailAddr.Address` | Validated with RFC-strict `EmailStr`; QBO's own validation may be looser — flagged in `docs/human_intervention_log.md` as a product decision to revisit. |
| `phone` | No | `PrimaryPhone.FreeFormNumber` | QBO stores phone as free text, no format enforced. |
| `billing_address.*` | No | `BillAddr.{Line1,Line2,City,CountrySubDivisionCode,PostalCode,Country}` | `CountrySubDivisionCode` is QBO's non-obvious name for state/province — worth calling out since it's the kind of field a human wouldn't guess without docs. |
| `currency` | Yes (defaults `USD`) | `CurrencyRef.value` | Only meaningful if the QBO company has multi-currency enabled; not verified whether a single-currency sandbox company rejects this field outright (A4/A5). |
| `is_active` | Yes (defaults `true`) | `Active` | |
| `erp_id` | *(output only)* | `Id` | Populated after create/read, never sent on create. |
| `erp_sync_token` | *(output only)* | `SyncToken` | QBO's optimistic-concurrency token, required on *update* (not used by this PoC, which only creates/reads) but captured now so an update workflow can reuse it later. |

Validation rules enforced client-side before any network call
(`canonical.py`, `pydantic`): `display_name` non-blank, max 100 chars; valid
email format if provided; `currency` normalized to uppercase 3-letter code;
`external_id` non-blank.

### 4.3 Documentation analysis (Phase 3)

| Topic | Finding | Source / confidence |
|---|---|---|
| API type | REST/JSON Accounting API v3 (there's also a legacy SOAP API and a separate Payments API — not used here). | Confirmed via multiple secondary sources. |
| Recommended API | Accounting API v3, `/customer` and `/query` endpoints. | Confirmed. |
| Auth | OAuth 2.0 Authorization Code grant (3-legged); 1-hour access tokens; refresh tokens rotate on every use and last up to 100 days if actively used. | Confirmed via secondary sources; the rotating-refresh-token behavior is the single most consequential detail for the token-store design (`qbo_auth.py`) and is worth a human double-checking on first live run. |
| Authorization / roles | The QBO user completing OAuth consent must have Admin or Accountant rights on that company. | Commonly documented; **not independently verified**. |
| Required account config | None known for Customer; Invoice would require existing Item/Account records (Section 4.1). | Inferred from QBO's data model, not confirmed against a live company. |
| Endpoints used | `GET /v3/company/{realmId}/companyinfo/{realmId}` (connectivity check), `POST /v3/company/{realmId}/customer` (create), `GET /v3/company/{realmId}/customer/{id}` (read), `GET /v3/company/{realmId}/query?query=...` (SQL-like query, used for duplicate-name lookup). | Confirmed shape via secondary sources; exact response envelope (`{"Customer": {...}}` / `{"QueryResponse": {...}}`) assumed consistent with widely-documented QBO conventions but not fetched from the primary reference in this session. |
| Pagination | `STARTPOSITION` / `MAXRESULTS` query params on the query endpoint. | Not exercised by this PoC (single-record lookups only) — documented for completeness, not implemented. |
| Filtering | SQL-like `query` parameter (e.g. `select * from Customer where DisplayName = '...'`). | Used directly in `qbo_client.find_customer_by_display_name`. |
| Idempotency | **No native idempotency-key header.** This is a real gap in QBO's API, not a documentation-analysis miss — confirmed by its absence from every source reviewed. Compensated at the application layer (Section 4.4). | Confirmed by absence, cross-checked against multiple sources. |
| Concurrency | Optimistic locking via `SyncToken`, required on update requests (mismatch → conflict error). Not exercised here since this PoC never updates. | Confirmed pattern, standard in QBO. |
| Rate limits | 500 requests/min per realm, 40 concurrent. | Secondary source (Satva Solutions); not independently verified. |
| Retries | No official SDK-provided backoff; Intuit's general guidance is exponential backoff on 429/5xx, which this PoC implements directly (`retry.py`). | Standard REST API guidance, not QBO-specific verified text. |
| Error handling | Errors return as a `Fault` JSON object (`{"Fault": {"Error": [{"Message", "Detail", "code"}], "type"}}`); HTTP status codes are also meaningful (400/401/403/404/429/5xx). Fault code `6240` = duplicate name. | Confirmed shape via multiple secondary sources and widely known QBO SDK behavior; the specific `6240` code is the one deliberately used for idempotency short-circuiting and should be the first thing verified live. |
| Webhooks | QBO supports webhooks for entity change events (requires a public HTTPS endpoint + signature verification). | Known to exist; **out of scope**, not used by this synchronous PoC. |
| Custom fields | Supported on transaction/sales forms, not on Customer master data, and limited in count. | Not used; A5 in Section 2. |
| Versioning | Path-based (`v3`); a `minorversion` query param exists for finer-grained changes. | Standard QBO convention. |
| Sandbox differences | Different API host (`sandbox-quickbooks.api.intuit.com` vs. `quickbooks.api.intuit.com`), otherwise same request/response shape; sandbox company is commonly pre-seeded with sample data. | Host difference confirmed via multiple sources; pre-seeding behavior flagged as "commonly reported, confirm live" in `docs/sandbox_test_procedure.md`. |
| Known limitations | No native idempotency keys; rotating single-use refresh tokens add real operational complexity; strict redirect-URI allowlisting. | Direct consequence of the above findings. |

**What could not be determined from documentation alone (this session):**
the exact primary-source request/response JSON schema (blocked by
`developer.intuit.com`'s JS-rendered doc explorer — WebFetch could not
render it), exact field length limits, and whether a fresh sandbox company
is truly pre-seeded with sample data in all cases. All three are the first
things `docs/sandbox_test_procedure.md` verifies.

### 4.4 Architecture

```
                         ┌─────────────────────────┐
   human (CLI / .env) ── │      cli.py (CLI)        │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │  service.py               │  orchestration:
                         │  CustomerSyncService       │  idempotency check →
                         └───┬──────────┬───────────┘  human approval →
                             │          │                create → read-back →
             ┌───────────────▼┐   ┌────▼────────────┐   audit
             │ canonical.py     │   │ idempotency.py   │
             │ (ERP-agnostic     │   │ audit.py          │
             │  Pydantic model)   │   └───────────────────┘
             └────────┬──────────┘
                       │
             ┌─────────▼──────────┐
             │ transform_qbo.py     │  ERP-specific mapping
             └─────────┬───────────┘
                       │
             ┌─────────▼──────────┐      ┌───────────────┐
             │ qbo_client.py        │──── │ retry.py        │  backoff on
             │ (HTTP + error norm)   │     │ errors.py        │  retriable
             └─────────┬────────────┘     └───────────────┘  errors only
                       │
             ┌─────────▼──────────┐
             │ qbo_auth.py           │  OAuth2 token cache + refresh
             │ (TokenStore, local file)│
             └────────────────────────┘
```

| Component | ERP-specific? | Reusable for a second connector? |
|---|---|---|
| `canonical.py` | No | Yes — this is the whole point of having it |
| `errors.py` (exception hierarchy) | No (the *normalizer function* is QBO-specific; the exception *classes* are not) | Yes — a NetSuite connector implements its own `normalize_netsuite_error` returning the same classes |
| `retry.py` | No | Yes, unchanged |
| `idempotency.py` | No | Yes, unchanged |
| `audit.py` | No | Yes, unchanged |
| `service.py` (orchestration shape) | No | Yes, same shape — swap in a different client/transform pair |
| `settings.py` | Partially | Config *shape* is reusable; specific fields (realm ID, redirect URI) are QBO-specific |
| `qbo_auth.py` | **Yes** | No — NetSuite's Client Credentials flow is a different (simpler) implementation |
| `qbo_client.py` | **Yes** | No — different base URL, endpoints, query language |
| `transform_qbo.py` | **Yes** | No — this is expected to be rewritten per ERP by design |
| `cli.py` | Mostly no | The approval-gate and write-refusal pattern is reusable; command names would extend |

**Human-review checkpoints** (mirroring the assignment's three-tier model):

- **AI-independent**: everything in the "AI, autonomous" rows of
  `docs/human_intervention_log.md` — doc research, schema/mapping proposal,
  code + test generation.
- **AI-with-approval**: the interactive `[y/N]` prompt in `cli.py` before
  every write; field-mapping choices flagged for review in
  `docs/human_intervention_log.md`.
- **Human-only**: account creation, credentials, OAuth consent, and the
  final "should we build a second ERP connector" business decision
  (Section 9).

**Security model**: secrets live only in a gitignored `.env` and a
gitignored local token-cache file (`qbo_auth.TokenStore`), written with an
atomic rename to avoid partial writes; nothing in the codebase logs a token
or client secret (`audit.py` deliberately only records IDs and outcomes,
never payloads containing secrets); the CLI refuses write commands outside
`QBO_ENVIRONMENT=sandbox`.

---

## 5. Implementation plan

| # | Task | AI responsibility | Human responsibility | Required input | Expected output | Validation |
|---|---|---|---|---|---|---|
| 1 | ERP + workflow selection | Research, compare, recommend | Confirm/override the recommendation | None blocking | Section 3–4 of this report | Human sign-off (pending) |
| 2 | Canonical schema + mapping | Design and implement | Review mapping choices | None blocking | `canonical.py`, `transform_qbo.py` | Unit tests (done, passing) |
| 3 | Error/retry/idempotency design | Design and implement | None (internal architecture) | None blocking | `errors.py`, `retry.py`, `idempotency.py` | Unit tests (done, passing) |
| 4 | HTTP client + OAuth handling | Implement | None blocking | None blocking | `qbo_client.py`, `qbo_auth.py` | Mocked tests (done, passing); real network path unverified |
| 5 | Orchestration + CLI | Implement | None blocking | None blocking | `service.py`, `cli.py` | Mocked end-to-end tests (done, passing) |
| 6 | Create Intuit dev account + app | N/A | **Required** | Email, acceptance of Intuit ToS | Client ID/Secret | Human confirms keys visible in dashboard |
| 7 | Populate `.env` | Can prepare the template | **Required** to fill real values | Client ID/Secret from task 6 | Local `.env` (never committed) | `erp-poc verify-connection` succeeds |
| 8 | OAuth consent flow | Can generate the exact URL/instructions | **Required** — browser login + click | Sandbox company login | `code` + `realmId` | Copy-paste into `scripts/initial_oauth_exchange.py`, script exits 0 |
| 9 | Live connectivity test | Can run once tokens exist | Trigger the run | None | Company name/ID printed | Manual visual check |
| 10 | Live create + read-back | Can run once tokens exist | **Approve the write** at the CLI prompt | None | New sandbox customer, confirmed read-back | Compare printed record to input JSON |
| 11 | Live negative-path tests | Can run/interpret results | Manually create a duplicate-name record in the QBO UI for one test | None | Clear, typed errors for each scenario in `docs/sandbox_test_procedure.md` §7 | Each error maps to the expected exception type |
| 12 | Record outcomes | Can draft the log entry | Confirm accuracy | Results from tasks 9–11 | New entry in `docs/human_intervention_log.md` | Human review |

Tasks 1–5 are complete as of this report. Tasks 6–12 require the human setup
described in Section 3.2 / `docs/sandbox_test_procedure.md` and have not run.

---

## 6. Codebase

Implemented under `src/erp_poc/` with tests under `tests/`. See
[`README.md`](README.md) for install/run instructions and project layout.
Highlights:

- Pydantic v2 models with real validation (`canonical.py`)
- Normalized, typed error hierarchy distinguishing retriable vs. non-retriable
  failures (`errors.py`)
- Exponential backoff with jitter, honoring `Retry-After` (`retry.py`)
- Application-layer idempotency (local store + live duplicate-name query),
  compensating for QBO's lack of a native idempotency key (`idempotency.py`,
  `service.py`)
- Append-only audit trail, secret-free by construction (`audit.py`)
- OAuth2 token cache with atomic writes, handling QBO's rotating refresh
  tokens (`qbo_auth.py`)
- CLI with a mandatory human-approval prompt before every write, and a
  hard refusal to write outside `QBO_ENVIRONMENT=sandbox` (`cli.py`)
- 34 tests, all passing, all offline: `pytest -q`

---

## 7. Test plan

| Category | Covered by | Status |
|---|---|---|
| Unit — canonical model validation | `tests/test_canonical.py` (required-field, blank-name, invalid-email, currency-normalization cases) | ✅ Implemented, passing |
| Unit — field mapping | `tests/test_transform_qbo.py` (full round-trip, missing-optional-fields, omission of absent fields from outbound payload) | ✅ Implemented, passing |
| Unit — retry/backoff | `tests/test_retry.py` (succeeds first try, retries then succeeds, does not retry non-retriable errors, gives up after max attempts, honors `Retry-After`) | ✅ Implemented, passing |
| Unit — idempotency store | `tests/test_idempotency.py` (miss, round-trip, persistence across instances, key isolation) | ✅ Implemented, passing |
| Mocked API — happy path | `tests/test_service_mocked.py::test_full_create_and_read_back_flow_success` | ✅ Implemented, passing |
| Mocked API — idempotency (local store hit) | `test_second_sync_uses_local_idempotency_store_and_skips_create` | ✅ Implemented, passing |
| Mocked API — duplicate-record handling | `test_live_duplicate_match_short_circuits_create` | ✅ Implemented, passing |
| Authentication | `test_401_on_create_surfaces_auth_error_without_retrying`; also `errors.py`'s `test_401_maps_to_auth_error` | ✅ Implemented, passing |
| Permissions | `errors.py`'s `test_403_maps_to_permission_error` | ✅ Implemented, passing |
| Rate limiting | `test_transient_429_on_create_is_retried_then_succeeds`; `errors.py`'s 429 tests | ✅ Implemented, passing |
| Malformed data | `test_canonical.py`'s validation-error cases (rejected before any network call) | ✅ Implemented, passing |
| Negative — human rejects approval | `test_human_rejects_approval_aborts_before_any_write` (confirms zero write calls occur) | ✅ Implemented, passing |
| Connectivity smoke test | `test_verify_connection_reads_company_info` | ✅ Implemented, passing |
| **Sandbox integration test** | `docs/sandbox_test_procedure.md` | ⏳ **Not yet run** — requires human-created credentials |

Run everything implemented so far: `pytest -q` → `34 passed`.

---

## 8. Feasibility report

**Conclusion: feasible with specific prerequisites.**

Evidence for feasibility:
- A complete, layered, tested integration codebase was produced in a single
  AI working session, from a cold start with zero prior code, covering
  auth, read, transform, write, read-back, validation, error normalization,
  retry/backoff, and application-level idempotency — all ten
  implementation requirements in the assignment's Phase 5 list.
- 34 automated tests pass, exercising the orchestration logic (including
  idempotency short-circuiting, human-approval gating, and retry behavior)
  without needing real credentials, which is itself evidence the design is
  testable independent of live access.
- The AI correctly identified and worked around a genuine access
  constraint (NetSuite's lack of self-service sandbox access) using live
  research rather than assuming from training data — directly satisfying
  the instruction not to claim sandbox availability without verification.
- The human-in-the-loop boundaries specified in the assignment (account
  creation, credentials, OAuth consent, per-write approval) are enforced in
  the code itself, not just described in prose: the CLI will not write
  outside `sandbox`, and will not write without an explicit `[y/N]` or
  `--yes`.

Prerequisites still outstanding before "feasible now" can be claimed:
1. A human must actually create the Intuit developer account and complete
   OAuth consent (~15–20 min, `docs/sandbox_test_procedure.md`) — nothing
   about this integration has touched a real API yet.
2. The primary-source QBO API reference should be read directly (not just
   via secondary sources) to confirm the field-mapping and error-code
   assumptions in Section 4.3 — the single most important documentation gap
   this session hit.
3. A human should review `transform_qbo.py` and the email-validation
   strictness decision noted in `docs/human_intervention_log.md`.

**Estimated engineering time saved** (qualitative, not measured against a
control): a manual build of this same scope — reading QBO's docs, designing
a canonical model, writing an OAuth token-refresh handler correctly
(rotating refresh tokens are an easy mistake to get wrong), implementing
retry/backoff, and writing 34 tests — would plausibly take an engineer new
to the QBO API 2–4 days. This session produced it in one sitting. That
estimate should be treated as directional, not measured, since no live
sandbox validation has occurred yet to confirm the code is actually correct
against the real API, only that it's internally consistent and passes its
own mocked tests.

**Security concerns identified, addressed in code:** no hard-coded secrets
(enforced by required, default-less settings fields that fail loudly if
missing); no secrets in the audit trail; local token/idempotency stores are
explicitly flagged as PoC-only, not production-grade (Section 2, A3).

**Operational risks identified, not yet addressed (by design, out of
scope):** no encryption at rest for the local token cache; no multi-process
safety on the idempotency/token files; no webhook-based change detection
(polling/on-demand only); update and delete operations are unimplemented.

**Documentation gaps encountered:** primary QBO API reference not
directly fetchable in this session (Section 4.3); NetSuite SDN approval
timeline unpublished; QBO sandbox pre-seeding behavior only "commonly
reported."

**Generated-code defects found during this session:** two test fixtures
used an RFC-reserved `.test` email domain that `email-validator` correctly
rejected — caught immediately by running the test suite and fixed. No
defects found in the implementation code itself during this session (only
test data), which should be read as "no defects found by the tests that
exist," not as a certification of correctness against the live API.

---

## 9. Scaling analysis

**Reusable when adding a second connector (e.g., NetSuite), per Section
4.4's table:** `canonical.py`'s model shape and validation pattern, the
entire `errors.py` exception hierarchy (a new `normalize_netsuite_error`
function would populate the same classes), `retry.py`, `idempotency.py`,
`audit.py` unchanged, and `service.py`'s orchestration shape (idempotency
check → approval gate → write → read-back → audit) unchanged aside from
swapping which client/transform pair it calls.

**Would need to be rebuilt per connector:** the auth module
(`qbo_auth.py`'s 3-legged OAuth token cache vs. NetSuite's Client
Credentials flow — likely simpler, ironically, since it skips the browser
consent step entirely), the HTTP client (`qbo_client.py` — different base
URL pattern, different query language), and the transform module
(`transform_qbo.py` — field names, required-field set, and error codes all
differ per ERP).

**Estimated work for ERP #2 (NetSuite), labeled as estimates only:**
- Auth module: **~0.5–1 day** (simpler flow than QBO, but first time
  through NetSuite's specific token endpoint and account-ID-based base URL
  scheme).
- HTTP client + error normalization: **~1 day**, assuming the canonical
  model and error hierarchy require no changes — mostly translating
  NetSuite's REST record API shape and whatever its fault/error JSON format
  turns out to be (not researched in this session).
- Field mapping: **~0.5–1 day**, plus **unknown, likely nontrivial** extra
  time if NetSuite's subsidiary/multi-book model requires extending
  `CanonicalCustomer` itself (which would also touch QBO's transform, to
  keep both ERPs honoring the same canonical shape).
- Tests: **~0.5 day**, largely following the existing mocked-test pattern.
- **Total estimate: ~2.5–4 engineer-days**, *not counting* NetSuite's
  unconfirmed sandbox-approval wait time from Section 3, which could easily
  dominate the actual calendar time even though it's near-zero engineering
  effort.

This is a meaningful drop from a from-scratch build specifically because
the canonical model, error taxonomy, retry/idempotency/audit
infrastructure, orchestration pattern, and human-checkpoint pattern don't
need to be redesigned — only re-implemented against a different API
surface. That is the core evidence this PoC set out to produce: the
*reusable 60%* is reusable, and the *ERP-specific 40%* is small and
well-isolated.
