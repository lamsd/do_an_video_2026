#!/usr/bin/env bash
# Removes only modules explicitly created by setup_virtual_audio.sh.
set -euo pipefail

STATE_FILE="${XDG_RUNTIME_DIR:-/tmp}/jitsi-emotion-lab-audio.env"
if [[ ! -f "$STATE_FILE" ]]; then
  echo "No Jitsi Emotion Lab module state file exists; nothing was removed."
  exit 0
fi
if ! command -v pactl >/dev/null 2>&1 || ! pactl info >/dev/null 2>&1; then
  echo "No reachable PulseAudio/PipeWire pactl server; cannot unload saved modules." >&2
  exit 1
fi

# State is generated with %q by the setup script; shellcheck disable is intentional here.
# shellcheck disable=SC1090
source "$STATE_FILE"
for module_id in "${SOURCE_MODULE_ID:-}" "${SINK_MODULE_ID:-}"; do
  if [[ -n "$module_id" ]]; then
    pactl unload-module "$module_id" 2>/dev/null || true
  fi
done
rm -f "$STATE_FILE"
echo "Removed virtual Jitsi Emotion Lab audio modules."

