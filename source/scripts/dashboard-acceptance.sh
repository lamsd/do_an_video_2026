#!/usr/bin/env sh
# Read-only UAT check for the application dashboard. It never requests or prints transcript text.
set -eu

usage() {
  echo "Usage: $0 [APPLICATION_MEETING_UUID]" >&2
  exit 2
}

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"

if [ ! -f settings.env ]; then
  echo "Missing settings.env in $project_dir" >&2
  exit 1
fi

meeting_id=${1:-}
[ "$#" -le 1 ] || usage
if [ -n "$meeting_id" ]; then
  python3 - "$meeting_id" <<'PY' >/dev/null
import sys
from uuid import UUID

UUID(sys.argv[1])
PY
fi

api_port=$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env)
dashboard_port=$(awk -F= '$1 == "DASHBOARD_PORT" { print $2; exit }' settings.env)
api_port=${api_port:-8088}
dashboard_port=${dashboard_port:-3000}
api_base="http://127.0.0.1:${api_port}"
dashboard_url="http://127.0.0.1:${dashboard_port}/"
app_user_id=${APP_USER_ID:-local-dev}

# This verifies Compose, backend readiness and the dashboard document. It does not expose settings.env.
./scripts/verify.sh

if [ -z "$meeting_id" ]; then
  echo "PASS: deployment is reachable. Supply an application meeting UUID to validate one completed dashboard run."
  echo "Dashboard: ${dashboard_url}"
  exit 0
fi

runs=$(curl --fail --silent --show-error \
  -H "X-App-User-Id: ${app_user_id}" \
  "${api_base}/v1/meetings/${meeting_id}/analysis")
run_id=$(printf '%s' "$runs" | python3 -c '
import json, sys
runs = json.load(sys.stdin)
if not runs:
    raise SystemExit("No analysis run exists for this meeting; run final analysis before UAT.")
run = runs[0]
if run.get("status") != "succeeded":
    raise SystemExit(f"Latest analysis run is {run.get(\"status\")}; wait for succeeded before UAT.")
print(run["id"])
')

overview=$(curl --fail --silent --show-error \
  -H "X-App-User-Id: ${app_user_id}" \
  "${api_base}/v1/meetings/${meeting_id}/analytics/overview?run_id=${run_id}")

printf '%s' "$overview" | python3 -c '
import json, sys

payload = json.load(sys.stdin)
required = ("run_id", "model_version", "preprocessing_version", "source_revision", "metrics")
missing = [key for key in required if payload.get(key) is None]
if missing:
    raise SystemExit("Dashboard overview is missing: " + ", ".join(missing))
if payload.get("status") != "succeeded":
    raise SystemExit("Dashboard overview does not represent a completed run.")
metrics = payload["metrics"]
metric_keys = ("unit_count", "accepted_unit_count", "predicted_unit_count", "prediction_coverage", "effective_coverage", "inference_total_ms")
missing_metrics = [key for key in metric_keys if key not in metrics]
if missing_metrics:
    raise SystemExit("Dashboard metrics are missing: " + ", ".join(missing_metrics))

print("PASS: dashboard acceptance data is complete (no transcript was requested).")
print("Meeting: " + sys.argv[1])
print("Run: " + payload["run_id"])
print("Model: " + payload["model_version"])
print("Preprocessing: " + payload["preprocessing_version"])
print("Revision: " + str(payload["source_revision"]))
print("Coverage: prediction={:.0%}, effective={:.0%}".format(
    metrics["prediction_coverage"], metrics["effective_coverage"]
))
print("Batch inference: " + str(metrics["inference_total_ms"]) + " ms")
' "$meeting_id"

echo "Dashboard: ${dashboard_url}"
