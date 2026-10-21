#!/usr/bin/env bash
set -euo pipefail

uv run pytest -q
uv run ruff check backend simulator tests
uv run mypy backend/app simulator
docker compose --env-file .env.example config >/dev/null
printf 'Static verification completed. Docker engine end-to-end execution is a separate step.\n'
