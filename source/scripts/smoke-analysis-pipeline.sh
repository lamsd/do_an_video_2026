#!/usr/bin/env sh
# Exercise API -> PostgreSQL -> Valkey Stream -> worker -> analytics API with synthetic data.
# The generated meeting and all dependent rows are removed on exit, including on failure.
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"

for command in docker curl python3; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command is unavailable: $command" >&2
    exit 1
  fi
done

if [ ! -f settings.env ]; then
  echo "Missing settings.env in $project_dir" >&2
  exit 1
fi

api_port=$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env)
api_port=${api_port:-8088}
api_base="http://127.0.0.1:${api_port}"
meeting_id=$(python3 -c 'import uuid; print(uuid.uuid4())')
segment_positive_id=$(python3 -c 'import uuid; print(uuid.uuid4())')
segment_negative_id=$(python3 -c 'import uuid; print(uuid.uuid4())')

cleanup() {
  # Every dependent table uses ON DELETE CASCADE. The generated UUID is the exact deletion target.
  docker compose --env-file settings.env exec -T postgres \
    psql -U meeting -d meeting -v ON_ERROR_STOP=1 \
    -c "DELETE FROM meetings WHERE id = '${meeting_id}'::uuid" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker compose --env-file settings.env exec -T postgres \
  psql -U meeting -d meeting -v ON_ERROR_STOP=1 <<SQL
INSERT INTO meetings (id, owner_id, platform, native_meeting_id, status, transcript_revision)
VALUES ('${meeting_id}'::uuid, 'local-dev', 'fixture', 'internal-smoke-${meeting_id}', 'completed', 1);
INSERT INTO transcript_segments
  (id, meeting_id, vexa_segment_id, speaker_key, speaker_name, language, text, start_seconds, end_seconds, is_final, retracted, revision)
VALUES
  ('${segment_positive_id}'::uuid, '${meeting_id}'::uuid, 'fixture-positive', 'speaker-a', 'Fixture A', 'vi', 'Cảm ơn bạn, công việc này rất tốt', 1700000000, 1700000004, true, false, 1),
  ('${segment_negative_id}'::uuid, '${meeting_id}'::uuid, 'fixture-negative', 'speaker-b', 'Fixture B', 'vi', 'Hiện tại có lỗi, việc này rất khó', 1700000005, 1700000009, true, false, 1);
SQL

curl --fail --silent --show-error \
  -X POST "${api_base}/v1/meetings/${meeting_id}/analysis?kind=final" \
  -H 'X-App-User-Id: local-dev' >/dev/null

attempt=0
while [ "$attempt" -lt 30 ]; do
  analysis=$(curl --fail --silent --show-error \
    -H 'X-App-User-Id: local-dev' "${api_base}/v1/meetings/${meeting_id}/analysis")
  status=$(printf '%s' "$analysis" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["status"])')
  if [ "$status" = "succeeded" ]; then
    break
  fi
  if [ "$status" = "failed" ]; then
    echo "Analysis worker marked the synthetic run as failed." >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 1
done

if [ "$status" != "succeeded" ]; then
  echo "Timed out waiting for the analysis worker." >&2
  exit 1
fi

overview=$(curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' "${api_base}/v1/meetings/${meeting_id}/analytics/overview")
units=$(curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' "${api_base}/v1/meetings/${meeting_id}/analytics/units")
timeline=$(curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' "${api_base}/v1/meetings/${meeting_id}/analytics/timeline")
run_id=$(printf '%s' "$overview" | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')
window=$(printf '%s' "$timeline" | python3 -c '
import json, sys
row = json.load(sys.stdin)[0]
print("{}|{}".format(row["start"], row["end"]))
')
window_start=${window%%|*}
window_end=${window#*|}
window_units=$(curl --fail --silent --show-error --get \
  -H 'X-App-User-Id: local-dev' \
  --data-urlencode "run_id=${run_id}" \
  --data-urlencode "window_start=${window_start}" \
  --data-urlencode "window_end=${window_end}" \
  "${api_base}/v1/meetings/${meeting_id}/analytics/units")
units_page_two=$(curl --fail --silent --show-error --get \
  -H 'X-App-User-Id: local-dev' \
  --data-urlencode "run_id=${run_id}" \
  --data-urlencode 'limit=1' \
  --data-urlencode 'offset=1' \
  "${api_base}/v1/meetings/${meeting_id}/analytics/units")

printf '%s\n%s\n%s\n%s\n' "$overview" "$units" "$window_units" "$units_page_two" | python3 -c '
import json, sys
overview, units, window_units, units_page_two = map(json.loads, sys.stdin)
assert overview["status"] == "succeeded"
assert overview["coverage"] == 1
assert len(units) == 2
assert {unit["label"] for unit in units} == {"positive", "negative"}
assert len(window_units) == 2
assert all(unit["run_id"] == overview["run_id"] for unit in window_units)
assert len(units_page_two) == 1
assert units_page_two[0]["unit_id"] == units[1]["unit_id"]
'

echo "PASS: synthetic fixture completed API -> queue -> worker -> analytics API, timeline evidence filter, and evidence pagination."
