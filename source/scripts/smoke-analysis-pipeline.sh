#!/usr/bin/env sh
# Exercise API -> PostgreSQL -> Valkey Stream -> worker -> analytics/SSE using
# synthetic data only. The exact fixture meeting and all dependent rows are
# removed on exit, including after a failed assertion.
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"

for command in docker curl python3 sed tail grep; do
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
dashboard_port=$(awk -F= '$1 == "DASHBOARD_PORT" { print $2; exit }' settings.env)
api_port=${api_port:-8088}
dashboard_port=${dashboard_port:-3000}
api_base="http://127.0.0.1:${api_port}"
dashboard_api_base="http://127.0.0.1:${dashboard_port}/api"
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

request_final_run() {
  curl --fail --silent --show-error \
    -X POST "${api_base}/v1/meetings/${meeting_id}/analysis?kind=final" \
    -H 'X-App-User-Id: local-dev' | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])'
}

wait_for_run() {
  run_id=$1
  attempt=0
  while [ "$attempt" -lt 30 ]; do
    overview=$(curl --fail --silent --show-error \
      -H 'X-App-User-Id: local-dev' \
      "${api_base}/v1/meetings/${meeting_id}/analytics/overview?run_id=${run_id}")
    status=$(printf '%s' "$overview" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
    if [ "$status" = "succeeded" ]; then
      return 0
    fi
    if [ "$status" = "failed" ]; then
      echo "Analysis worker marked synthetic run ${run_id} as failed." >&2
      exit 1
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
  echo "Timed out waiting for analysis run ${run_id}." >&2
  exit 1
}

capture_sse() {
  # curl exits 28 when --max-time closes a healthy, deliberately open stream.
  set +e
  output=$(curl --silent --no-buffer --max-time 2 "$@")
  status=$?
  set -e
  if [ "$status" -ne 0 ] && [ "$status" -ne 28 ]; then
    echo "SSE request failed with curl exit code ${status}." >&2
    exit "$status"
  fi
  printf '%s' "$output"
}

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

first_run=$(request_final_run)
wait_for_run "$first_run"
overview=$(curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${api_base}/v1/meetings/${meeting_id}/analytics/overview?run_id=${first_run}")
units=$(curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${api_base}/v1/meetings/${meeting_id}/analytics/units?run_id=${first_run}")
timeline=$(curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${api_base}/v1/meetings/${meeting_id}/analytics/timeline?run_id=${first_run}")
manifest_one=$(curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${api_base}/v1/meetings/${meeting_id}/analytics/evidence-manifest?run_id=${first_run}")

printf '%s\n%s\n%s\n%s\n' "$overview" "$units" "$timeline" "$manifest_one" | python3 -c '
import json, sys
overview, units, timeline, manifest = map(json.loads, sys.stdin)
assert overview["status"] == "succeeded"
assert overview["source_revision"] == 1
assert overview["coverage"] == 1
assert len(units) == 2
assert {unit["label"] for unit in units} == {"positive", "negative"}
assert len(timeline) == 1
assert manifest["analysis_run"]["input_segment_count"] == 2
assert {row["source_segment_revision"] for row in manifest["input_segments"]} == {1}
'

# Repeated request against the same meeting/revision/version must return the same durable run.
duplicate_run=$(request_final_run)
[ "$duplicate_run" = "$first_run" ] || {
  echo "Analysis request was not idempotent for the same source revision." >&2
  exit 1
}

# Owner scoping must not reveal another caller's meeting state.
foreign_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H 'X-App-User-Id: another-user' \
  "${api_base}/v1/meetings/${meeting_id}/analytics/overview")
[ "$foreign_status" = "404" ] || {
  echo "Cross-meeting access was not rejected; expected 404, got ${foreign_status}." >&2
  exit 1
}

# Simulate a late provider revision. The first run must retain its immutable rev-1 snapshot.
docker compose --env-file settings.env exec -T postgres \
  psql -U meeting -d meeting -v ON_ERROR_STOP=1 <<SQL
UPDATE transcript_segments
SET text = 'Nội dung đã được Vexa chỉnh sửa', revision = 2
WHERE id = '${segment_positive_id}'::uuid;
UPDATE meetings SET transcript_revision = 2 WHERE id = '${meeting_id}'::uuid;
SQL

second_run=$(request_final_run)
[ "$second_run" != "$first_run" ] || {
  echo "A late transcript revision reused the old analysis run." >&2
  exit 1
}
wait_for_run "$second_run"
manifest_one_after=$(curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${api_base}/v1/meetings/${meeting_id}/analytics/evidence-manifest?run_id=${first_run}")
manifest_two=$(curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${api_base}/v1/meetings/${meeting_id}/analytics/evidence-manifest?run_id=${second_run}")
printf '%s\n%s\n' "$manifest_one_after" "$manifest_two" | python3 -c '
import json, sys
first, second = map(json.loads, sys.stdin)
assert first["analysis_run"]["source_revision"] == 1
assert second["analysis_run"]["source_revision"] == 2
assert {row["source_segment_revision"] for row in first["input_segments"]} == {1}
assert 2 in {row["source_segment_revision"] for row in second["input_segments"]}
'

# Simulate an explicit provider retraction; the next snapshot must exclude it.
docker compose --env-file settings.env exec -T postgres \
  psql -U meeting -d meeting -v ON_ERROR_STOP=1 <<SQL
UPDATE transcript_segments SET retracted = true, revision = 2
WHERE id = '${segment_negative_id}'::uuid;
UPDATE meetings SET transcript_revision = 3 WHERE id = '${meeting_id}'::uuid;
SQL

third_run=$(request_final_run)
wait_for_run "$third_run"
manifest_three=$(curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${api_base}/v1/meetings/${meeting_id}/analytics/evidence-manifest?run_id=${third_run}")
printf '%s' "$manifest_three" | python3 -c '
import json, sys
manifest = json.load(sys.stdin)
assert manifest["analysis_run"]["source_revision"] == 3
assert manifest["analysis_run"]["input_segment_count"] == 1
assert len(manifest["input_segments"]) == 1
'

# A reconnect from the last delivered SSE event must not replay old events.
initial_stream=$(capture_sse -H 'X-App-User-Id: local-dev' \
  "${dashboard_api_base}/v1/meetings/${meeting_id}/events")
last_event_id=$(printf '%s\n' "$initial_stream" | sed -n 's/^id: //p' | tail -n 1)
[ -n "$last_event_id" ] || {
  echo "SSE stream did not provide an event ID." >&2
  exit 1
}
resumed_stream=$(capture_sse -H 'X-App-User-Id: local-dev' \
  -H "Last-Event-ID: ${last_event_id}" \
  "${dashboard_api_base}/v1/meetings/${meeting_id}/events")
if printf '%s\n' "$resumed_stream" | grep -q '^id: '; then
  echo "SSE reconnect replayed an already delivered event." >&2
  exit 1
fi

echo "PASS: synthetic API/queue/worker run, idempotency, late revision, retraction, owner isolation, and SSE reconnect passed."
