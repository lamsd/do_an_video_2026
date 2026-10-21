#!/usr/bin/env bash
# Create a PulseAudio/PipeWire-compatible virtual microphone for Jitsi.
set -euo pipefail

STATE_FILE="${XDG_RUNTIME_DIR:-/tmp}/jitsi-emotion-lab-audio.env"
SINK_NAME="JitsiLabSink"
SOURCE_NAME="JitsiLabMic"

if ! command -v pactl >/dev/null 2>&1; then
  echo "pactl was not found. Install PulseAudio utilities or PipeWire's pulse compatibility layer." >&2
  exit 1
fi
if ! pactl info >/dev/null 2>&1; then
  echo "No user PulseAudio/PipeWire server is reachable. Run this in the logged-in desktop session." >&2
  exit 1
fi

if pactl list short sinks | awk '{print $2}' | grep -Fxq "$SINK_NAME"; then
  echo "Virtual sink $SINK_NAME already exists. Run scripts/check_virtual_audio.sh for its source name."
  exit 0
fi

SINK_MODULE_ID="$(pactl load-module module-null-sink sink_name="$SINK_NAME" sink_properties="device.description=Jitsi_Emotion_Lab_Output")"
# The monitor of a null sink is an input source; remapping gives Jitsi a stable friendly name.
SOURCE_MODULE_ID="$(pactl load-module module-remap-source master="${SINK_NAME}.monitor" source_name="$SOURCE_NAME" source_properties="device.description=Jitsi_Emotion_Lab_Microphone")"

umask 077
{
  printf 'SINK_MODULE_ID=%q\n' "$SINK_MODULE_ID"
  printf 'SOURCE_MODULE_ID=%q\n' "$SOURCE_MODULE_ID"
  printf 'SINK_NAME=%q\n' "$SINK_NAME"
  printf 'SOURCE_NAME=%q\n' "$SOURCE_NAME"
} > "$STATE_FILE"

echo "Ready: select '$SOURCE_NAME' as the microphone in the Jitsi browser settings."
echo "Generated WAV files can be routed with scripts/play_audio_to_jitsi.sh <file.wav>."

