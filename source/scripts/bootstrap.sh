#!/usr/bin/env sh
set -eu

if ! docker info >/dev/null 2>&1; then
  echo "Docker Engine is unavailable. Start Docker and run this script again." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required." >&2
  exit 1
fi

if [ ! -f settings.env ]; then
  cp settings.env.example settings.env
  chmod 600 settings.env
  echo "Created settings.env. Fill every CHANGE_ME value, configure transcription, then create VEXA_API_KEY after Vexa is healthy."
else
  echo "settings.env already exists; it was not changed."
fi
