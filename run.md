# Running the Mumtaz & Co ERP POC

This is the verified process for getting the app running locally — it's
been run end-to-end (backend, migrations, seed data, frontend, login) as
of this writing. Two small fixes were needed along the way; they're
already applied in the codebase, noted at the bottom for context.

## 1. Backend (Django + DRF)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py makemigrations   # generates migrations for every app
python manage.py migrate

python manage.py seed_demo_data   # wipes in and reseeds all demo data
python manage.py runserver        # http://127.0.0.1:8000
```

`seed_demo_data` seeds everything in one shot: roles & permissions,
warehouses, brands/SKUs, channels & pricing, shops, DRs/employees/sales
targets, opening stock & safety stock levels, a sample purchase order, and
~14 days of sample sales orders. It's idempotent — re-running it skips
records that already exist (matched by number/name) rather than
duplicating or erroring — and prints the login list below when it
finishes.

Quick API smoke test:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/token/ \
  -d "username=owner&password=demopass123"
# should return {"refresh": "...", "access": "..."}
```

## 2. Frontend (React + Vite)

In a second terminal:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev       # http://localhost:5173
```

Open http://localhost:5173 — you'll land on the login screen.

## 3. Logging in

All seeded users share the password **`demopass123`**. Pick the role you
want to test as:

| Role                  | Username           |
|-----------------------|---------------------|
| Owner                 | `owner`             |
| Distribution Manager  | `dm_sargodha`       |
| Field Sales Officer   | `fso_sargodha`      |
| Sales Manager         | `salesmgr_sargodha` |
| Warehouse Staff       | `warehouse_sargodha`|
| Distribution Rep (DR) | `dr_anayat`         |

Owner is a superuser and sees every module; the other roles are scoped by
`accounts/management/commands/seed_roles.py` (`ROLE_MODEL_PERMISSIONS`) —
log in as each one to see the sidebar/permissions differ.

## Fixes applied to get here

- `core` was missing from `INSTALLED_APPS` in `backend/config/settings.py`
  — without it, `manage.py seed_demo_data` isn't discovered at all.
- `reports/views.py`'s dashboard endpoint used `TruncDate` on
  `SalesOrder.order_date`, which is already a `DateField` (not
  `DateTimeField`). That combination throws `OperationalError:
  user-defined function raised exception` on SQLite. Fixed by grouping on
  the field directly instead of truncating it.
- `core/management/commands/seed_demo_data.py`'s sales-order seeding used
  a counter that always restarted at 1 and an unconditional `.create()`,
  so re-running the command after a first successful run hit a `UNIQUE
  constraint failed: distribution_salesorder.so_number` — contradicting
  its own "safe to re-run" docstring. Fixed to `get_or_create` on
  `so_number`, matching the pattern the rest of the file already uses.

Both are already in the codebase — nothing further to do, just documented
here so the next person doesn't have to re-diagnose them.
