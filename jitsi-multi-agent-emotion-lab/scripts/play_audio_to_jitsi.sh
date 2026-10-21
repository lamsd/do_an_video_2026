#!/usr/bin/env bash
# One process may send audio at a time, so agent speech cannot overlap.
set -euo pipefail

SINK_NAME="JitsiLabSink"
LOCK_FILE="${XDG_RUNTIME_DIR:-/tmp}/jitsi-emotion-lab-playback.lock"

if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Usage: $0 /absolute/or/relative/path/to/generated.wav" >&2
  exit 64
fi
if ! command -v paplay >/dev/null 2>&1; then
  echo "paplay was not found. Install PulseAudio utilities or PipeWire pulse tools." >&2
  exit 1
fi
if ! pactl list short sinks | awk '{print $2}' | grep -Fxq "$SINK_NAME"; then
  echo "$SINK_NAME is unavailable. Run scripts/setup_virtual_audio.sh first." >&2
  exit 2
fi

if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK_FILE"
  flock 9
fi
paplay --device="$SINK_NAME" "$1"

