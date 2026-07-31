# Invoices — Phase 2 assessment (not implemented in this phase)

**Decision: deferred.** Per the brief, invoice support is only implemented if
it can be added "cleanly without destabilizing the completed customer/vendor
functionality." Having built and deployed the customer/vendor app, it's
clear invoices are a meaningfully different shape of problem — not a small
extension of `PartyWeb` — and taking them on now would risk the working
system for a feature that was explicitly optional this phase. This document
is the "clear implementation plan" the brief asks for instead.

## Why invoices don't fit the existing abstraction

Customer and Vendor are both flat QBO "Name List" entities — that's exactly
why one `CanonicalParty` model and one `PartyWeb` class could serve both
with almost no entity-specific code (see `party_views.py`). Invoice is a
QBO **Transaction** entity: it's a header (customer, date, currency) plus a
list of **line items**, each referencing a QBO **Item** (product/service)
and carrying its own quantity/rate/amount, plus optional tax data. None of
`canonical.py`, `transform_qbo.py`, `service.py`'s `PartySyncService`, or
the generic form/confirm templates can represent that without changes —
this is additive new code, not a config change to existing code.

## Required building blocks

1. **Customer selection** — Already have the data (`CanonicalCustomer` +
   `PartySyncService.search()`). New UI need: a picker (typeahead or
   dropdown) on the invoice form instead of free-text entry, so a user
   can't create an invoice against a customer that doesn't exist in QBO.
2. **Item (product/service) selection** — Not currently supported at all.
   QBO requires every invoice line to reference an existing `Item` by ID;
   this app has no read path for Items yet. Needs: `QBOClient.search_entities`
   generalizes to `Item` easily (same query-language mechanism already
   used for Customer/Vendor search), but the UI needs an item picker, and
   **items cannot be created by this app** in phase 2 — only selected from
   whatever the sandbox company already has. This is a real dependency on
   account-specific setup (see below).
3. **Line items** — Each line needs `ItemRef`, `Qty`, `UnitPrice` (or just
   `Amount`), and QBO computes `Amount = Qty * UnitPrice` if both are given
   (server-side; not independently verified in this phase — flag for the
   sandbox test). The web form needs a repeating line-item UI (add/remove
   rows), which is the first place this app would need more than "minimal
   vanilla JavaScript" — a real, if small, frontend complexity jump.
4. **Quantities and rates** — Straightforward numeric fields once the line
   editor exists; validation (non-negative, reasonable precision) is new
   Pydantic model work (`CanonicalInvoiceLine`).
5. **Taxes** — The biggest unknown. QBO sandbox companies commonly have
   "Automated Sales Tax" enabled, which changes how tax is calculated and
   represented on the wire (`TxnTaxDetail`) compared to older manual
   tax-code companies, and this difference **was not exercised or
   confirmed in this phase** (no live invoice test was run). Getting this
   wrong either silently miscalculates tax or gets the create request
   rejected — this needs a dedicated round of doc research and live sandbox
   testing before implementation, not just an inferred field mapping.
6. **Account-specific dependencies** — Unlike Customer/Vendor (which work
   in a bare sandbox company), Invoice creation depends on the company
   already having at least one `Item` (and, if tax is involved, tax codes
   configured) — configuration this app cannot create on the user's
   behalf. A human would need to confirm the shared sandbox company has at
   least one usable Item before this feature would work at all.

## What would need to be built

| Component | New or reused |
|---|---|
| `CanonicalInvoiceLine`, `CanonicalInvoice` models | New (`canonical.py` addition) |
| `transform_qbo_invoice.py` (Invoice <-> canonical mapping) | New — Invoice's nested `Line[]` shape has no analog in `transform_qbo.py` |
| `QBOClient.search_entities("item", ...)` | Reused mechanism, new call sites |
| `QBOClient` create/read for Invoice | Reused `_request` plumbing, new thin methods (mirrors `create_entity`/`get_entity`, Invoice already fits the generic entity shape for create/read — only the *payload construction* is new) |
| An `InvoiceService` (not `PartySyncService` — no DisplayName-based duplicate check makes sense for invoices; idempotency would key on our `external_id` only) | New |
| Web templates: line-item editor (JS), customer picker, item picker | New — the first meaningfully new frontend pattern in this app |
| Tests: line math, tax (once researched), duplicate/idempotency semantics for a transaction (not master-data) type | New |

## Estimate (an estimate, not a commitment)

Roughly **2–3 additional engineer-days** of focused work, dominated less by
the QBO API calls (those follow the same patterns already proven for
Customer/Vendor) and more by: (a) the line-item editing UI, and (b)
resolving the sales-tax question against a real sandbox company before
writing any tax-handling code. Recommend spending the first half-day purely
on research + a manual sandbox test of `POST /v3/company/{realmId}/invoice`
with a minimal line (no tax) before committing to a design.

## Recommended next step

Confirm the shared sandbox company has at least one `Item` (Customers &
Vendors app doesn't need this, so it was never checked), then do a
throwaway manual test — either via the CLI pattern or QBO's own API
Explorer — of a minimal Invoice create/read round trip to settle the tax
question with evidence before scoping this as a real phase-2 task.
