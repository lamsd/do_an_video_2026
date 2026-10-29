#!/usr/bin/env sh
# Control the Vexa meetings-only stack using the single source/settings.env file.
set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
config_file=${MEETING_CONFIG_FILE:-"$root_dir/settings.env"}
vexa_dir="$root_dir/vexa/deploy/meetings-only"
action=${1:-}
legacy_config="$vexa_dir/project.env"

usage() {
  cat <<'EOF'
Usage: ./scripts/vexa-selfhost.sh <import-legacy-config|sync-transcription-config|check|start|status|verify|mint-token>

Uses source/settings.env by default. Set MEETING_CONFIG_FILE to use another file.
EOF
}

if [ ! -r "$config_file" ]; then
  echo "Missing configuration: $config_file. Copy settings.env.example to settings.env first." >&2
  exit 1
fi

if [ "$action" = "import-legacy-config" ]; then
  if [ ! -r "$legacy_config" ]; then
    echo "Missing legacy Vexa configuration: $legacy_config." >&2
    exit 1
  fi
  vexa_keys='IMAGE_TAG API_GATEWAY_HOST_PORT ADMIN_API_PORT MEETING_API_PORT RUNTIME_API_PORT POSTGRES_HOST_PORT MINIO_HOST_PORT MINIO_CONSOLE_HOST_PORT DB_NAME DB_USER DB_PASSWORD MINIO_ACCESS_KEY MINIO_SECRET_KEY MINIO_BUCKET MINIO_ENDPOINT MINIO_SECURE ADMIN_TOKEN INTERNAL_API_SECRET DOCKER_GID LOG_LEVEL BROWSER_IMAGE TRANSCRIPTION_SERVICE_URL TRANSCRIPTION_SERVICE_TOKEN TRANSCRIPTION_MODEL TRANSCRIBE_ENABLED RECORDING_ENABLED VEXA_SYSTEM_WEBHOOK_URL VEXA_SYSTEM_WEBHOOK_SECRET VEXA_SYSTEM_WEBHOOK_ALLOW_PRIVATE_HTTP'
  temp_file=$(mktemp "${config_file}.tmp.XXXXXX")
  trap 'rm -f "$temp_file"' EXIT HUP INT TERM
  awk -v legacy="$legacy_config" -v keys="$vexa_keys" '
    BEGIN {
      count = split(keys, ordered, " ")
      for (i = 1; i <= count; i++) wanted[ordered[i]] = 1
      while ((getline line < legacy) > 0) {
        if (line ~ /^[A-Za-z_][A-Za-z0-9_]*=/) {
          split(line, pair, "=")
          if (pair[1] in wanted) replacement[pair[1]] = line
        }
      }
      close(legacy)
    }
    {
      if ($0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/) {
        split($0, pair, "=")
        if (pair[1] in wanted) {
          if (!(pair[1] in emitted) && pair[1] in replacement) print replacement[pair[1]]
          emitted[pair[1]] = 1
          next
        }
      }
      print
    }
    END {
      for (i = 1; i <= count; i++) {
        key = ordered[i]
        if (!(key in emitted) && key in replacement) print replacement[key]
      }
    }
  ' "$config_file" > "$temp_file"
  chmod 600 "$temp_file"
  mv "$temp_file" "$config_file"
  trap - EXIT HUP INT TERM
  echo "Imported Vexa settings into $config_file. The legacy project.env was not changed."
  exit 0
fi

if [ "$action" = "sync-transcription-config" ]; then
  transcription_env="$root_dir/vexa/deploy/transcription/.env"
  if [ ! -r "$transcription_env" ]; then
    echo "Missing transcription configuration: $transcription_env." >&2
    exit 1
  fi
  host_ip=${HOST_LAN_IP:-$(hostname -I | awk '{for (i = 1; i <= NF; i++) if ($i ~ /^192\\.168\\./ || $i ~ /^10\\./) {print $i; exit}}')}
  if [ -z "$host_ip" ]; then
    echo "Cannot determine a LAN IP. Run with HOST_LAN_IP=<your-host-ip>." >&2
    exit 1
  fi
  temp_file=$(mktemp "${config_file}.tmp.XXXXXX")
  trap 'rm -f "$temp_file"' EXIT HUP INT TERM
  awk -F= -v transcription_env="$transcription_env" -v host_ip="$host_ip" '
    BEGIN {
      while ((getline line < transcription_env) > 0) {
        if (line ~ /^API_TOKEN=/) token = substr(line, index(line, "=") + 1)
      }
      close(transcription_env)
      if (token == "" || token == "CHANGE_ME" || token ~ /^</) exit 2
    }
    /^TRANSCRIPTION_SERVICE_URL=/ { print "TRANSCRIPTION_SERVICE_URL=http://" host_ip ":8083"; url_written = 1; next }
    /^TRANSCRIPTION_SERVICE_TOKEN=/ { print "TRANSCRIPTION_SERVICE_TOKEN=" token; token_written = 1; next }
    { print }
    END {
      if (!url_written) print "TRANSCRIPTION_SERVICE_URL=http://" host_ip ":8083"
      if (!token_written) print "TRANSCRIPTION_SERVICE_TOKEN=" token
    }
  ' "$config_file" > "$temp_file" || {
    rm -f "$temp_file"
    echo "API_TOKEN is missing or a placeholder in $transcription_env." >&2
    exit 1
  }
  chmod 600 "$temp_file"
  mv "$temp_file" "$config_file"
  trap - EXIT HUP INT TERM
  echo "Synced the transcription endpoint and token into $config_file."
  exit 0
fi

config_value() {
  awk -F= -v wanted="$1" '
    $0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/ && $1 == wanted {
      value = substr($0, index($0, "=") + 1)
      found = 1
    }
    END {
      if (found) print value
    }
  ' "$config_file"
}

compose_project_name=$(config_value COMPOSE_PROJECT_NAME)
vexa_compose_project_name=$(config_value VEXA_COMPOSE_PROJECT_NAME)
vexa_network=$(config_value VEXA_NETWORK)
transcription_service_url=$(config_value TRANSCRIPTION_SERVICE_URL)
transcription_service_token=$(config_value TRANSCRIPTION_SERVICE_TOKEN)
gateway_port=$(config_value API_GATEWAY_HOST_PORT)
admin_port=$(config_value ADMIN_API_PORT)
admin_token=$(config_value ADMIN_TOKEN)
browser_image=$(config_value BROWSER_IMAGE)
image_tag=$(config_value IMAGE_TAG)
browser_image=${browser_image:-"vexaai/vexa-bot:${image_tag:-v012}"}

required='DB_PASSWORD MINIO_ACCESS_KEY MINIO_SECRET_KEY ADMIN_TOKEN INTERNAL_API_SECRET'
for key in $required; do
  value=$(config_value "$key")
  if [ -z "$value" ] || [ "$value" = "CHANGE_ME" ]; then
    echo "Configuration error: set $key in $config_file." >&2
    exit 1
  fi
done

case "$action" in
  check)
    if [ -n "$compose_project_name" ]; then
      echo "Configuration error: remove COMPOSE_PROJECT_NAME from $config_file." >&2
      exit 1
    fi
    if [ "$vexa_compose_project_name" != "vexa-meetings" ]; then
      echo "Configuration error: VEXA_COMPOSE_PROJECT_NAME must be vexa-meetings." >&2
      exit 1
    fi
    if [ "$vexa_network" != "vexa-meetings_vexa" ]; then
      echo "Configuration error: VEXA_NETWORK must be vexa-meetings_vexa." >&2
      exit 1
    fi
    if [ -z "$transcription_service_url" ] || [ -z "$transcription_service_token" ]; then
      echo "Warning: transcription is not configured; Vexa can start, but transcribing bots will return 503." >&2
    elif case "$transcription_service_url$transcription_service_token" in *'<'*|*'>'*) true ;; *) false ;; esac; then
      echo "Configuration error: replace <...> transcription placeholders with real values in $config_file." >&2
      exit 1
    fi
    (cd "$vexa_dir" && COMPOSE_PROJECT_NAME="$vexa_compose_project_name" docker compose --env-file "$config_file" -f compose.yaml config --quiet)
    echo "Configuration is valid."
    ;;
  start)
    (cd "$vexa_dir" && COMPOSE_PROJECT_NAME="$vexa_compose_project_name" docker compose --env-file "$config_file" -f compose.yaml up -d)
    ;;
  status)
    (cd "$vexa_dir" && COMPOSE_PROJECT_NAME="$vexa_compose_project_name" docker compose --env-file "$config_file" -f compose.yaml ps)
    ;;
  verify)
    gateway_port=${gateway_port:-18156}
    curl --fail --silent --show-error "http://127.0.0.1:${gateway_port}/health" >/dev/null
    status=$(curl --silent --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:${gateway_port}/agent/health")
    if [ "$status" != "404" ]; then
      echo "Expected /agent/health to be absent (404), got $status." >&2
      exit 1
    fi
    if ! docker image inspect "$browser_image" >/dev/null 2>&1; then
      echo "Missing Vexa bot runner image: $browser_image" >&2
      echo "Download it with: docker pull $browser_image" >&2
      exit 1
    fi
    echo "Verified: Vexa meetings-only gateway and bot runner image are ready."
    ;;
  mint-token)
    admin_port=${admin_port:-18157}
    ADMIN_API_URL="http://127.0.0.1:${admin_port}" \
      EMAIL="${EMAIL:-meeting-intelligence@localhost}" \
      SCOPES="${SCOPES:-bot,tx}" \
      ADMIN_TOKEN="$admin_token" \
      "$root_dir/vexa/deploy/compose/bin/provision-token"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
