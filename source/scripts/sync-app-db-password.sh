#!/usr/bin/env sh
# Synchronize the application PostgreSQL role password with settings.env.
# This updates only the database role password: it never removes volumes, tables, or data.
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"

if [ ! -f settings.env ]; then
  echo "Missing settings.env in $project_dir" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI is not installed or not available on PATH." >&2
  exit 1
fi

app_db_password=$(awk -F= '$1 == "POSTGRES_PASSWORD" { print substr($0, index($0, "=") + 1); exit }' settings.env)
if [ -z "$app_db_password" ] || [ "$app_db_password" = "CHANGE_ME" ]; then
  echo "POSTGRES_PASSWORD must be set to a non-placeholder value in settings.env." >&2
  exit 1
fi

# settings.env documents a URL-safe password. Reject quotes rather than risk constructing
# invalid SQL or displaying part of a secret in an error message.
case "$app_db_password" in
  *"'"*)
    echo "POSTGRES_PASSWORD must be URL-safe and must not contain a single quote." >&2
    exit 1
    ;;
esac

docker compose --env-file settings.env exec -T \
  -e NEW_APP_DB_PASSWORD="$app_db_password" \
  postgres sh -ceu '
    psql -U meeting -d meeting -v ON_ERROR_STOP=1 \
      -c "ALTER ROLE CURRENT_USER PASSWORD '\''$NEW_APP_DB_PASSWORD'\''" >/dev/null
  '

echo "Application PostgreSQL role password synchronized without exposing its value."
