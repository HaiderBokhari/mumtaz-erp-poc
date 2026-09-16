# Mumtaz & Co Distribution ERP — CLAUDE.md

This briefs Claude Code (or anyone picking this up) on what this project
is, why it's structured the way it is, and what to do next.

## What this is

A POC ERP for **Mumtaz & Co**, a PTC (Pakistan Tobacco Company) cigarette
distributor in Sargodha, Pakistan, with branches in Bhalwal and Bhera. The
business currently runs entirely on Excel — this system is meant to
replace that. The full requirement is in `docs/requirements/`:

- `Requirement_for_MumtazCo.pdf` — the original scope document (problem
  statement + feature list, organized by module: Purchase, Inventory,
  Distribution & Channel, Accounts, HR, Access Control).
- `Mumtaz_Co_questionnaire_Answer.docx` — the client's answers to a
  follow-up discovery questionnaire. **This is the more specific source of
  truth** where it disagrees with or adds detail to the PDF (e.g. exact
  numbers of DRs/employees, which report groupings matter, the FBR
  July–June vs. internal Jan–Dec fiscal year quirk, BIZOM as the sales data
  source).
- `How_PTC_Distributor_Works.docx` — domain background: PTC's channel
  taxonomy (DD/VDD/WS/VWS/MANDI), the DR → FSO → Distribution Manager field
  hierarchy, Primaries vs. Secondaries, Unique/Active Handlers, the SD-20
  register, and why Mumtaz & Co runs two parallel inventories (Company
  On-Hand vs. Actual On-Hand).

**Read all three before making product decisions.** A lot of the modeling
choices in this codebase (stock ledger as source of truth, channel × SKU
price history, DR codes like `SGD_SGD_DR01`, safety-stock alerts, the
fixed-column sales upload) trace directly back to specific lines in these
docs — the docstrings in the code point to which requirement they satisfy.

The client also has ~20+ years of real operational data in Excel (closing
stock sheets, daily sales registers, monthly targets) that were used to
inform the brand/SKU/warehouse shape in `core/management/commands/
seed_demo_data.py`, but were **not** copied into this repo (they're real
business data, not schema). If you need to see the original shape again,
ask the user for them — the last analysis found: stock-by-brand sheets
keyed by warehouse (Sargodha+RP / Bhalwal / Bhera) with SMALL/LARGE/RETURN
rows per SKU column; an "SD-20" sheet with the exact daily-register columns
(Balance, Received, DSD/Shop/VDSD/V-W/Army/Whole Sale, Running Total, Free/
Scheme Stock, Closing Balance); and a "Targets" sheet with DR × channel ×
SKU monthly volume targets.

## Stack & why

- **Django + DRF**, SQLite for the POC (swap for Postgres — one dict in
  `config/settings.py` — before anything beyond a local demo).
- **JWT auth** (`djangorestframework-simplejwt`) so the API can be driven
  by both the React SPA and, later, a mobile app for DRs without session
  cookie complications.
- **React + TypeScript + Vite + Tailwind**, plain `axios` + React state
  (no React Query / Redux) — deliberately minimal for a POC; reach for a
  data-fetching library once the number of screens grows past what
  `useEffect` + local state can hold comfortably.
- **Access control rides on Django's own Group/Permission system**, not a
  bespoke roles table. `accounts/management/commands/seed_roles.py` is the
  single place that decides which role gets create/edit/view/delete on
  which feature (model) — see `ROLE_MODEL_PERMISSIONS` there. `accounts/
  permissions.py::RolePermission` is the DRF permission class every
  ViewSet uses; it maps the DRF action to a Django permission codename and
  checks it against the user (Owner is a superuser and bypasses this
  entirely). If you add a model that needs API access, add it to that
  dict — nothing works by default, roles are opt-in per feature.

## The stock ledger pattern (read this before touching inventory)

`warehouses.StockLedgerEntry` is **append-only and is the single source of
truth** for all stock movement. `warehouses.StockLevel` is a cache, kept in
sync automatically by `StockLedgerEntry.save()` (see the model — every
insert nudges the matching `StockLevel` row via `F('quantity') + delta`).

Every module that moves stock creates a `StockLedgerEntry` rather than
touching `StockLevel` directly:
- `purchasing.PurchaseOrder.receive()` → `PURCHASE_IN`
- `purchasing.PurchaseReturn.submit()` → `PURCHASE_RETURN_OUT`
- `distribution.SalesOrder.confirm()` → `SALE_OUT`
- `distribution.SalesReturn.apply()` → `SALE_RETURN_IN`
- `warehouses.StockTransfer.dispatch()` / `.receive()` → `TRANSFER_OUT` / `TRANSFER_IN`
- `warehouses.StockAdjustment.apply()` → `ADJUSTMENT` (damage/loss/stolen/count correction)
- `core.seed_demo_data` → `OPENING_BALANCE`

If you add a new stock-moving feature, follow this pattern — create a
ledger entry, don't mutate `StockLevel` by hand. This is also what makes
the "two parallel inventories" problem in `How_PTC_Distributor_Works.docx`
tractable later: a second ledger dimension (or a `book` field on
`StockLedgerEntry`) can separate Company-On-Hand from Actual-On-Hand
without redesigning anything.

## What's fully built vs. stubbed

**Fully built** (models + API + Django admin, most with a frontend page):
accounts (roles/users/profiles), catalog (brand/SKU/channel/pricing),
warehouses (stock ledger/levels/transfers/adjustments/safety stock),
purchasing (POs/returns), distribution (shops/sales orders/returns/
payments/targets/PTC upload), hr (employees/salary/leave), reports
(dashboard).

**Deliberately stubbed** — `accounting/models.py` only has `Party` (used as
`PurchaseOrder.supplier` and referenced conceptually by Shop billing) and a
minimal `ChartOfAccount`/`AccountGroup`. None of these are exposed via API
yet; they're admin-only. **Not implemented at all**: double-entry
vouchers (payment/journal/expense), automatic posting of distribution/
purchasing transactions to the ledger, financial statements (income,
balance sheet, cashflow), running party-ledger balances with date-range
queries, aged receivables/payables. `distribution.Shop.outstanding_balance`
is a placeholder (invoiced − collected) standing in for a real party
ledger until that module exists.

**Not started**: bar-code scanning (questionnaire answer #16 says this
isn't needed for now), batch/expiry tracking (needed specifically for
VELO — questionnaire #18), a real DR mobile app, opening-balance data
migration tooling (the client's historical data starts January 2026 —
questionnaire #31).

## Suggested build order from here

1. **Smoke-test what exists** (see below) — this was built without a
   working Python/Node environment (sandboxed, no package registry
   access), so nothing has actually been run. Expect a handful of typos or
   import-order issues; fix forward rather than rewriting.
2. **Accounting module, properly**: `AccountGroup`/`ChartOfAccount` exist;
   add `Voucher` (payment/journal/expense per requirement doc), post
   distribution & purchasing transactions to it automatically (e.g. a
   confirmed `SalesOrder` should generate the relevant journal entries),
   build `PartyLedgerEntry` with running balances, then the three
   financial statements. This is the biggest remaining piece.
3. **Batch/expiry tracking for VELO** — add `batch_number`/`expiry_date` to
   `StockLedgerEntry` (or a new `Batch` model SKUs can optionally track),
   surface it in the receive/dispatch flows.
4. **Aged receivables/payables** report once the party ledger exists
   (questionnaire #3: "mandatory").
5. **Data migration tooling** — a management command to load the closing
   balances the client will provide as `OPENING_BALANCE` ledger entries
   (same pattern `seed_demo_data` already uses), keyed from Jan 2026.
6. **Tighten the PTC sales upload** (`distribution/imports.py`) against a
   *real* BIZOM/PTC export once the client shares a sample — the current
   column mapping in `TEMPLATE_COLUMNS` is a best-effort placeholder, not
   a confirmed format.

## Conventions to keep following

- Every model/endpoint that maps to a specific requirement-doc bullet has
  a docstring citing it (e.g. "requirement doc, Purchase #1"). Keep doing
  this — it's what makes it possible to check completeness against the
  PDF later.
- ViewSets: `permission_classes = [RolePermission]` (from
  `accounts.permissions`) unless the endpoint is intentionally
  Owner-only (`IsAdminUser`, used for `accounts.UserViewSet`) or
  read-only-and-safe-for-any-authenticated-user (`IsAuthenticated`, used
  for `reports.DashboardView`).
- Money fields: `DecimalField`, never float. Quantities: `DecimalField`
  too (PTC volumes are fractional — 1 M = 1000 sticks, and the real sheets
  carry 2-3 decimal places).
- Auto-numbering (`PO-2026-00001`, `SO-2026-00001`) happens server-side in
  the ViewSet's `perform_create`, not the frontend — see
  `purchasing/views.py::_next_po_number` for the pattern if you add more
  numbered documents (`PurchaseReturn.return_number`,
  `StockTransfer.transfer_number` are still manually entered; give them
  the same treatment if you build a frontend form for them).
- Frontend: one page per module under `frontend/src/pages/`, plain
  `axios` calls in `useEffect`, Tailwind utility classes (see
  `src/index.css` for the shared `.btn-primary`/`.card`/`.input`/
  `.data-table` classes rather than repeating Tailwind soup inline).

## Smoke-test checklist (do this first)

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py makemigrations   # should produce migrations for every app cleanly
python manage.py migrate
python manage.py seed_demo_data   # should complete without error and print demo logins
python manage.py runserver
# in another shell:
curl -X POST http://127.0.0.1:8000/api/auth/token/ -d "username=owner&password=demopass123"
# should return an access + refresh token
```

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
# open http://localhost:5173, log in as owner / demopass123
```

If `makemigrations` wants to create migrations, that's expected — no
migration files were generated in this environment (no Django install
available to run the command). Run it, review the generated migrations
look sane, then `migrate`.
