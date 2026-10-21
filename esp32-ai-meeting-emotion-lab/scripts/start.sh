#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
  printf 'Missing .env. Run ./scripts/setup.sh first.\n' >&2
  exit 1
fi
docker compose up --build
