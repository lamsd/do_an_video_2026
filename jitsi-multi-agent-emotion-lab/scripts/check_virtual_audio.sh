#!/usr/bin/env bash
set -euo pipefail

SINK_NAME="JitsiLabSink"
SOURCE_NAME="JitsiLabMic"

if ! command -v pactl >/dev/null 2>&1 || ! pactl info >/dev/null 2>&1; then
  echo "FAIL: no reachable PulseAudio/PipeWire pactl server." >&2
  exit 1
fi

if pactl list short sinks | awk '{print $2}' | grep -Fxq "$SINK_NAME"; then
  echo "OK: output sink $SINK_NAME is available"
else
  echo "MISSING: output sink $SINK_NAME (run scripts/setup_virtual_audio.sh)" >&2
  exit 2
fi

if pactl list short sources | awk '{print $2}' | grep -Fxq "$SOURCE_NAME"; then
  echo "OK: virtual microphone $SOURCE_NAME is available"
else
  echo "MISSING: virtual microphone $SOURCE_NAME (run scripts/setup_virtual_audio.sh)" >&2
  exit 3
fi

echo "Next: open Jitsi device settings and select '$SOURCE_NAME'."

