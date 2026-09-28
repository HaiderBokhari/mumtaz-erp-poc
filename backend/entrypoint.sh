#!/bin/sh
# Runs on every container boot before gunicorn starts. migrate is always
# safe to re-run (Django tracks applied migrations); seed_demo_data is
# explicitly documented as safe to re-run (get_or_create throughout), so
# this is what makes a freshly-provisioned Postgres database usable on
# the very first deploy with no manual shell step.
set -e

python manage.py migrate --noinput

if [ "$DJANGO_SEED_DEMO_DATA" = "True" ]; then
    python manage.py seed_demo_data
fi

# Additive and idempotent (only ever adds a missing JournalEntry, never
# deletes anything) — safe to run unconditionally on every boot. Exists so
# a PO/SO that reached RECEIVED/CONFIRMED before the accounting module
# existed still ends up with its accounting entry, without needing shell
# access on free-tier Render to run it by hand.
python manage.py backfill_accounting_entries

exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2
