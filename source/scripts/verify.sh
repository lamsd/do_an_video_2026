#!/usr/bin/env sh
set -eu

dashboard_port=$(awk -F= '$1 == "DASHBOARD_PORT" { print $2; exit }' settings.env 2>/dev/null || true)
api_port=$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env 2>/dev/null || true)
dashboard_port=${dashboard_port:-3000}
api_port=${api_port:-8088}

docker compose --env-file settings.env ps
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/ready" >/dev/null
curl --fail --silent --show-error "http://127.0.0.1:${dashboard_port}/" >/dev/null
echo "Verified: backend health and Dashboard are reachable."
