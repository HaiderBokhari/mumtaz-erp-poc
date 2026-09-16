# Mumtaz & Co — Distribution ERP (POC)

A proof-of-concept ERP for a PTC (Pakistan Tobacco Company) distributor in
Sargodha, built from `Requirement for MumtazCo.pdf`, the client
questionnaire answers, and the real Excel workbooks the business currently
runs on (`CLOSING JAN -25.xlsx`, `SALES FILE AUG 2026.xlsx`,
`Mumtaz & Co H1 Sales26.xlsx`).

Backend: **Django + Django REST Framework** (JWT auth, role-based
permissions on top of Django's own Group/Permission system).
Frontend: **React + TypeScript + Vite + Tailwind CSS**, talking to the API
over JWT.

## What's in this POC

Implemented end-to-end (models + API + admin, most with a frontend screen too):

- **Access control** — fixed roles (Owner, Distribution Manager, FSO, Sales
  Manager, Warehouse Staff, DR) as Django Groups with per-feature
  create/edit/view/delete permissions; branch-restricted logins.
- **Catalog** — Brand & SKU lifecycle, channel lifecycle (DD/VDD/WS/VWS/MANDI
  × filer/non-filer), channel-wise price history, SKU cost history.
- **Warehouses & inventory** — append-only stock ledger (single source of
  truth), cached stock levels, inter-warehouse transfers with an in-transit
  state, damaged/lost/stolen adjustments, safety-stock alerts.
- **Purchasing** — purchase orders tied to a PTC SAP reference, an
  internal-approval step for the out-station branches (Bhera, Bhalwal),
  purchase return claims, PO history grouped by SKU/brand.
- **Distribution** — shop/retailer lifecycle, sales orders, sales returns,
  payment receipts (cash/bank/cheque, incl. post-dated), DR-wise monthly
  targets vs. achievement, a fixed-column CSV/XLSX upload pipeline for PTC/
  BIZOM sales files, daily closing summary and grouped sales summaries.
- **HR** — employee records, monthly salary + commission payments, salary
  slips, leave requests/approval.
- **Reports** — one aggregated owner-facing dashboard endpoint (stock
  value, today's/MTD sales, receivables, collections, low-stock alerts,
  30-day trend, channel breakdown).

Deliberately stubbed for a later pass (see `CLAUDE.md` → "Suggested build
order"): full double-entry accounting (vouchers, financial statements,
running party ledgers). The `accounting` app currently only has a Chart of
Accounts and a `Party` model that Purchasing/Distribution already point at,
so the real thing can be layered in without touching those apps' schemas.

## Prerequisites

- Python 3.10+ and pip, with normal internet access (this scaffold was
  built in a sandboxed environment with **no package-registry access**, so
  none of the `pip`/`npm` installs below have been run or verified here —
  do that first, and expect to fix the odd typo).
- Node.js 18+ and npm.

## Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_data # creates roles, demo users, brands/SKUs, a PO, 15 days of sales
python manage.py createsuperuser  # optional, if you don't want to use the seeded "owner" login
python manage.py runserver
```

The API is now at `http://127.0.0.1:8000/api/`, and the Django admin at
`http://127.0.0.1:8000/admin/`.

### Demo logins (after `seed_demo_data`)

All passwords are `demopass123`.

| Role | Username |
|---|---|
| Owner (superuser) | `owner` |
| Distribution Manager | `dm_sargodha` |
| Field Sales Officer | `fso_sargodha` |
| Sales Manager | `salesmgr_sargodha` |
| Warehouse Staff | `warehouse_sargodha` |
| Distribution Representative | `dr_anayat` (also `dr_raza`, `dr_moavia`, `dr_naeem`, `dr_tayyab`) |

## Frontend setup

```bash
cd frontend
npm install
cp .env.example .env    # VITE_API_BASE_URL defaults to http://127.0.0.1:8000/api
npm run dev
```

Open `http://localhost:5173` and log in with one of the demo accounts above.

## Using this with Claude Code

`CLAUDE.md` at the repo root briefs Claude Code on the architecture, the
conventions used throughout (e.g. the stock ledger pattern, the
RolePermission class, how new modules should be wired in), what's still
stubbed, and a suggested order to keep building in. Open this folder in
Claude Code and it will pick that up automatically — a good first prompt is
something like:

> Read CLAUDE.md, then run the backend smoke-test steps it describes and
> fix anything that doesn't come up clean.

## Repo layout

```
backend/
  config/          Django project settings/urls
  accounts/        Users, roles/permissions, profile (branch, DR code)
  catalog/         Brand, SKU, Channel, ChannelPrice
  warehouses/      Warehouse, stock ledger, transfers, adjustments, safety stock
  purchasing/      PurchaseOrder, PurchaseReturn
  distribution/    Shop, SalesOrder, SalesReturn, PaymentReceipt, SalesTarget, PTC upload
  accounting/      STUB: Party, Chart of Accounts (see CLAUDE.md)
  hr/              Employee, SalaryPayment, LeaveRequest
  reports/         Dashboard aggregation endpoint
  core/            seed_demo_data management command
frontend/
  src/pages/       One page per module (Dashboard, Catalog, Warehouses, POs, Shops, SOs)
  src/api/         Axios client with JWT auth + refresh
  src/context/     Auth context (roles, login/logout)
```
