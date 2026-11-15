#!/usr/bin/env sh
# Restart every local service needed for a Meeting Intelligence Jitsi demo.
# The command preserves PostgreSQL, Valkey, MinIO and model volumes.
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
settings_file="$project_dir/settings.env"
transcription_dir="$project_dir/vexa/deploy/transcription"
transcription_env="$transcription_dir/.env"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

config_value() {
  awk -F= -v wanted="$1" '
    $0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/ && $1 == wanted {
      print substr($0, index($0, "=") + 1)
      exit
    }
  ' "$settings_file"
}

transcription_config_value() {
  awk -F= -v wanted="$1" '
    $0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/ && $1 == wanted {
      print substr($0, index($0, "=") + 1)
      exit
    }
  ' "$transcription_env"
}

run_with_retry() {
  label=$1
  shift
  attempt=1
  while [ "$attempt" -le 3 ]; do
    if "$@"; then
      return 0
    fi
    if [ "$attempt" -eq 3 ]; then
      fail "$label failed after ${attempt} attempts."
    fi
    echo "Waiting for Docker to finish a previous operation; retrying $label..." >&2
    sleep 3
    attempt=$((attempt + 1))
  done
}

wait_http() {
  label=$1
  url=$2
  attempt=1
  while [ "$attempt" -le 45 ]; do
    if curl --fail --silent --show-error --max-time 3 "$url" >/dev/null 2>&1; then
      echo "PASS: $label"
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  fail "$label did not become ready: $url"
}

command -v docker >/dev/null 2>&1 || fail "Docker CLI is not installed or not on PATH."
docker info >/dev/null 2>&1 || fail "Docker Engine is unavailable. Start Docker and try again."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."
[ -r "$settings_file" ] || fail "Missing $settings_file"
[ -r "$transcription_env" ] || fail "Missing $transcription_env"

api_port=$(config_value API_PORT)
dashboard_port=$(config_value DASHBOARD_PORT)
gateway_port=$(config_value API_GATEWAY_HOST_PORT)
transcription_port=$(transcription_config_value TRANSCRIPTION_LB_PORT)
api_port=${api_port:-8088}
dashboard_port=${dashboard_port:-3000}
gateway_port=${gateway_port:-18156}
transcription_port=${transcription_port:-8083}

echo "Restarting transcription service..."
(
  cd "$transcription_dir"
  docker compose --env-file "$transcription_env" \
    -f docker-compose.yml -f docker-compose.cpu.yml restart
  docker compose --env-file "$transcription_env" \
    -f docker-compose.yml -f docker-compose.cpu.yml up -d --no-recreate
)

echo "Restarting Vexa meetings stack..."
(
  cd "$project_dir"
  ./scripts/vexa-selfhost.sh restart
)

echo "Restarting Meeting Intelligence application..."
(
  cd "$project_dir"
  # A demo restart must not apply pending Compose or environment changes.  It
  # still creates a missing service, but leaves existing containers in place
  # for the following explicit restart (avoiding a Docker removal race).
  run_with_retry "application startup" docker compose --env-file "$settings_file" up -d --no-recreate
  run_with_retry "application restart" docker compose --env-file "$settings_file" restart
)

wait_http "Transcription service" "http://127.0.0.1:${transcription_port}/health"
wait_http "Vexa gateway" "http://127.0.0.1:${gateway_port}/health"
wait_http "Application backend" "http://127.0.0.1:${api_port}/ready"
wait_http "Dashboard" "http://127.0.0.1:${dashboard_port}/"
wait_http "Dashboard API proxy" "http://127.0.0.1:${dashboard_port}/api/v1/meetings?limit=1"

echo
echo "Demo stack is ready. Open: http://localhost:${dashboard_port}/"
echo "Existing meeting bots may have disconnected during the restart; create a new bot for the demo."
