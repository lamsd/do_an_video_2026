#!/usr/bin/env sh
# Read-only runtime audit for the Meeting Intelligence deployment.
# It intentionally never prints settings.env values or container environment variables.
set -u

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

api_port=$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env)
dashboard_port=$(awk -F= '$1 == "DASHBOARD_PORT" { print $2; exit }' settings.env)
api_port=${api_port:-8088}
dashboard_port=${dashboard_port:-3000}

echo "Meeting Intelligence runtime audit"
echo "Timestamp (UTC): $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo
echo "New stack (source/compose.yaml)"
docker compose --env-file settings.env ps || true
echo "Expected API:       http://127.0.0.1:${api_port}/ready"
echo "Expected dashboard: http://127.0.0.1:${dashboard_port}/"

if command -v curl >/dev/null 2>&1; then
  if curl --fail --silent --show-error "http://127.0.0.1:${api_port}/ready" >/dev/null; then
    echo "Readiness: PASS"
  else
    echo "Readiness: FAIL"
  fi
else
  echo "Readiness: SKIPPED (curl is unavailable)"
fi

echo
echo "Legacy stack containers (must not be used for the current demo)"
docker ps --format '{{.Names}}|{{.Status}}|{{.Ports}}' \
  | awk -F'|' '$1 ~ /^meeting-intelligence-backend-(backend|worker|dashboard|postgres|redis)-/' || true

echo
echo "Audit scope: no credentials, transcript content, or container environment values were displayed."
