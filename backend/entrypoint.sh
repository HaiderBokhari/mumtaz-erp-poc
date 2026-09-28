#!/bin/sh
# Runs on every container boot before gunicorn starts. migrate is always
# safe to re-run (Django tracks applied migrations); seed_demo_data is
# explicitly documented as safe to re-run (get_or_create throughout), so
# this is what makes a freshly-provisioned Postgres database usable on
# the very first deploy with no manual shell step.
set -e

# Opt-in, defaults to unset/False. Only for wiping a still-empty demo
# database back to a clean slate (e.g. after a schema change that a
# get_or_create reseed can't retrofit onto already-existing rows) — never
# flip this on once the database holds real data, since it deletes
# everything. Free-tier Render has no shell access, hence a flag here
# instead of running `manage.py flush` by hand.
if [ "$DJANGO_RESET_DEMO_DATA" = "True" ]; then
    python manage.py flush --noinput
fi

python manage.py migrate --noinput

if [ "$DJANGO_SEED_DEMO_DATA" = "True" ]; then
    python manage.py seed_demo_data
fi

exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2
