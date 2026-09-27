#!/usr/bin/env sh
set -eu

: "${EMAIL:=meeting-intelligence@localhost}"
: "${SCOPES:=bot,tx}"

admin_token=$(awk -F= '$1 == "ADMIN_TOKEN" { print substr($0, index($0, "=") + 1); exit }' project.env)
admin_port=$(awk -F= '$1 == "ADMIN_API_PORT" { print $2; exit }' project.env)
: "${admin_token:?ADMIN_TOKEN is missing from project.env}"
admin_port=${admin_port:-18057}

ADMIN_TOKEN="$admin_token" \
ADMIN_API_URL="http://127.0.0.1:${admin_port}" \
EMAIL="$EMAIL" SCOPES="$SCOPES" \
../compose/bin/provision-token

