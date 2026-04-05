#!/bin/sh
set -eu

required_vars="DATABASE_URL DJANGO_SECRET_KEY TRACKER_INGEST_TOKEN TRACKER_BOOTSTRAP_ADMIN_EMAIL TRACKER_BOOTSTRAP_ADMIN_PASSWORD"

for var in $required_vars; do
  value=$(printenv "$var" || true)
  if [ -z "$value" ]; then
    echo "Missing required environment variable: $var" >&2
    exit 1
  fi
done

python manage.py migrate --noinput
python manage.py bootstrap_admin
python manage.py collectstatic --noinput

exec "$@"
