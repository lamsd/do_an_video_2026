#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
  cp .env.example .env
  printf 'Created .env from .env.example. Replace development passwords before using a real broker.\n'
fi

if [[ ! -d .venv ]]; then
  uv venv
fi
uv pip install -e '.[dev]'
printf 'Python environment is ready. Run ./scripts/start.sh for the Docker simulation.\n'
