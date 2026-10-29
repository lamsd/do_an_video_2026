#!/usr/bin/env sh
# Safe local configuration helper for Meeting Intelligence.
#
# This script is intentionally the only supported writer for settings.env in
# the operator workflow.  The browser never receives secrets and cannot start
# Docker containers.  Enter secrets in a local terminal only.
set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
config_file=${MEETING_CONFIG_FILE:-"$root_dir/settings.env"}
action=${1:-}

usage() {
  cat <<'EOF'
Usage: ./scripts/runtime-settings.sh <status|guide|configure-vexa|configure-model|apply|wizard>

  status           Show safe configuration state (never prints secret values).
  guide            Print the recommended setup/run order without reading secrets.
  configure-vexa   Prompt privately for a Vexa API key and save it locally.
  configure-model  Set the model adapter/version/threshold and optional artifact metadata.
  apply            Build and force-recreate backend, worker and dashboard.
  wizard           Run the Vexa and model setup steps, then optionally apply them.

Use MEETING_CONFIG_FILE=/path/to/settings.env to target a different local file.
EOF
}

if [ ! -r "$config_file" ]; then
  echo "Missing configuration: $config_file. Run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

config_value() {
  awk -F= -v wanted="$1" '
    $0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/ && $1 == wanted {
      value = substr($0, index($0, "=") + 1)
      found = 1
    }
    END { if (found) print value }
  ' "$config_file"
}

config_value_or_default() {
  configured_value=$(config_value "$1")
  if [ -n "$configured_value" ]; then
    printf '%s\n' "$configured_value"
  else
    printf '%s\n' "$2"
  fi
}

is_configured() {
  candidate=$(config_value "$1")
  [ -n "$candidate" ] && [ "$candidate" != "CHANGE_ME" ]
}

# Values are passed in the child environment, not as process arguments, so a
# secret is neither echoed nor placed in an `awk -v` command line.
set_value() {
  setting_key=$1
  setting_value=$2
  temp_file=$(mktemp "${config_file}.tmp.XXXXXX")
  trap 'rm -f "$temp_file"' EXIT HUP INT TERM
  SETTING_KEY="$setting_key" SETTING_VALUE="$setting_value" awk '
    BEGIN {
      key = ENVIRON["SETTING_KEY"]
      value = ENVIRON["SETTING_VALUE"]
    }
    $0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/ {
      split($0, pair, "=")
      if (pair[1] == key) {
        if (!written++) print key "=" value
        next
      }
    }
    { print }
    END { if (!written) print key "=" value }
  ' "$config_file" > "$temp_file"
  chmod 600 "$temp_file"
  mv "$temp_file" "$config_file"
  trap - EXIT HUP INT TERM
}

private_prompt() {
  prompt=$1
  if [ ! -t 0 ]; then
    echo "Secret entry requires an interactive local terminal." >&2
    exit 1
  fi
  printf '%s' "$prompt" >&2
  trap 'stty echo; printf "\\n" >&2; exit 130' HUP INT TERM
  stty -echo
  IFS= read -r private_value
  stty echo
  trap - HUP INT TERM
  printf '\n' >&2
}

prompt_value() {
  prompt=$1
  default_value=$2
  printf '%s [%s]: ' "$prompt" "$default_value" >&2
  IFS= read -r entered_value
  if [ -z "$entered_value" ]; then
    entered_value=$default_value
  fi
}

show_status() {
  printf '%-32s %s\n' "VEXA_API_KEY" "$(is_configured VEXA_API_KEY && echo configured || echo missing)"
  printf '%-32s %s\n' "VEXA_WEBHOOK_SECRET" "$(is_configured VEXA_WEBHOOK_SECRET && echo configured || echo missing)"
  printf '%-32s %s\n' "MODEL_ARTIFACT_DIR" "$(is_configured MODEL_ARTIFACT_DIR && echo configured || echo not-required-or-missing)"
  printf '%-32s %s\n' "MODEL_ARTIFACT_SHA256" "$(is_configured MODEL_ARTIFACT_SHA256 && echo configured || echo not-required-or-missing)"
  printf '%-32s %s\n' "CLASSIFIER_ADAPTER" "$(config_value_or_default CLASSIFIER_ADAPTER rules)"
  printf '%-32s %s\n' "MODEL_VERSION" "$(config_value_or_default MODEL_VERSION baseline-rules-v2)"
  printf '%-32s %s\n' "PREPROCESSING_VERSION" "$(config_value_or_default PREPROCESSING_VERSION 2026-09-v1)"
  printf '%-32s %s\n' "SENTIMENT_CONFIDENCE_THRESHOLD" "$(config_value_or_default SENTIMENT_CONFIDENCE_THRESHOLD 0.60)"
  echo "Secret values, API URLs and artifact paths are intentionally not printed."
}

show_guide() {
  cat <<'EOF'
Meeting Intelligence local setup

1. Verify the Vexa self-host runner:
   ./scripts/vexa-selfhost.sh verify

2. If VEXA_API_KEY is missing, invalid, or was exposed, mint a replacement key:
   ./scripts/vexa-selfhost.sh mint-token
   The token is printed once in this terminal. Do not paste it in a browser, chat or Git.

3. Store the replacement key privately and choose the model configuration:
   ./scripts/runtime-settings.sh wizard

4. Build and recreate backend, worker and dashboard. Database volumes are retained:
   ./scripts/runtime-settings.sh apply

5. Confirm readiness and open the Dashboard:
   ./scripts/verify.sh

Changing settings.env requires step 4. `docker compose restart` alone does not reload env_file.
EOF
}

configure_vexa() {
  private_prompt "Paste the replacement Vexa API key (input hidden): "
  case "$private_value" in
    vxa_?*) ;;
    *)
      echo "VEXA_API_KEY must start with vxa_. Nothing was saved." >&2
      exit 1
      ;;
  esac
  set_value VEXA_API_KEY "$private_value"
  unset private_value
  echo "Saved VEXA_API_KEY locally. The value was not printed. Run apply to recreate services."
}

configure_model() {
  current_adapter=$(config_value CLASSIFIER_ADAPTER)
  current_version=$(config_value MODEL_VERSION)
  current_preprocessing=$(config_value PREPROCESSING_VERSION)
  current_threshold=$(config_value SENTIMENT_CONFIDENCE_THRESHOLD)
  prompt_value "Classifier adapter (rules or tfidf-logreg)" "${current_adapter:-rules}"
  adapter=$entered_value
  case "$adapter" in rules|tfidf-logreg) ;; *) echo "Only rules or tfidf-logreg is supported." >&2; exit 1 ;; esac
  prompt_value "Model version" "${current_version:-baseline-rules-v2}"
  model_version=$entered_value
  prompt_value "Preprocessing version" "${current_preprocessing:-2026-09-v1}"
  preprocessing_version=$entered_value
  prompt_value "Sentiment confidence threshold (0 to 1)" "${current_threshold:-0.60}"
  threshold=$entered_value
  if ! awk -v value="$threshold" 'BEGIN { exit !(value ~ /^(0(\.[0-9]+)?|1(\.0+)?)$/) }'; then
    echo "Threshold must be a number from 0 to 1." >&2
    exit 1
  fi
  set_value CLASSIFIER_ADAPTER "$adapter"
  set_value MODEL_VERSION "$model_version"
  set_value PREPROCESSING_VERSION "$preprocessing_version"
  set_value SENTIMENT_CONFIDENCE_THRESHOLD "$threshold"
  if [ "$adapter" = "tfidf-logreg" ]; then
    prompt_value "Trusted artifact directory mounted at /models" "$(config_value MODEL_ARTIFACT_DIR)"
    artifact_dir=$entered_value
    prompt_value "Artifact SHA-256" "$(config_value MODEL_ARTIFACT_SHA256)"
    artifact_hash=$entered_value
    if [ -z "$artifact_dir" ] || ! printf '%s' "$artifact_hash" | awk 'length($0) == 64 && $0 ~ /^[0-9a-fA-F]+$/ { valid = 1 } END { exit !valid }'; then
      echo "tfidf-logreg requires a mounted artifact directory and a 64-character SHA-256." >&2
      exit 1
    fi
    set_value MODEL_ARTIFACT_DIR "$artifact_dir"
    set_value MODEL_ARTIFACT_SHA256 "$artifact_hash"
  fi
  echo "Saved model configuration locally. Run apply to rebuild and recreate services."
}

apply_settings() {
  echo "Checking configuration, then rebuilding and recreating backend, worker and dashboard…"
  (
    cd "$root_dir"
    docker compose --env-file "$config_file" config --quiet
    docker compose --env-file "$config_file" up -d --build --force-recreate backend worker dashboard
  )
  echo "Configuration applied. Run ./scripts/verify.sh to confirm readiness."
}

run_wizard() {
  echo "Local setup wizard. Secrets stay in this terminal and are not sent to the dashboard."
  configure_vexa
  configure_model
  printf 'Build and apply these settings now? [y/N]: ' >&2
  IFS= read -r answer
  case "$answer" in y|Y|yes|YES) apply_settings ;; *) echo "Settings saved only. Run ./scripts/runtime-settings.sh apply when ready." ;; esac
}

case "$action" in
  status) show_status ;;
  guide) show_guide ;;
  configure-vexa) configure_vexa ;;
  configure-model) configure_model ;;
  apply) apply_settings ;;
  wizard) run_wizard ;;
  *) usage >&2; exit 2 ;;
esac
