#!/usr/bin/env bash
set -euo pipefail

required=(docker uv)
optional=(pio idf.py)

for command in "${required[@]}"; do
  if command -v "$command" >/dev/null 2>&1; then
    printf 'OK       %s\n' "$command"
  else
    printf 'MISSING  %s\n' "$command"
  fi
done

for command in "${optional[@]}"; do
  if command -v "$command" >/dev/null 2>&1; then
    printf 'OPTIONAL %s available\n' "$command"
  else
    printf 'OPTIONAL %s unavailable (needed only for firmware work)\n' "$command"
  fi
done
