# Truy xuất dữ liệu và thu evidence cho báo cáo

> Các lệnh trong tài liệu này là read-only, trừ phần cuối cùng ghi file evidence local. Dùng chúng sau khi stack đã build theo [Hướng dẫn build từng bước](SETTINGS_AND_RUN_GUIDE.md). Không lưu secret, audio hoặc raw transcript vào Git/khóa luận.

## 1. Chuẩn bị biến local

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source

API_PORT="$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env)"
API_PORT="${API_PORT:-8088}"
API_BASE="http://127.0.0.1:${API_PORT}"
APP_USER_ID="${APP_USER_ID:-local-dev}"

# Thay UUID bằng Application Meeting UUID do Dashboard/API trả về.
MEETING_ID='<APPLICATION_MEETING_UUID>'
```

## 2. Runtime, trạng thái service và tài nguyên

```bash
./scripts/runtime-status.sh
./scripts/verify.sh
docker compose --env-file settings.env ps
docker stats --no-stream $(docker compose --env-file settings.env ps -q backend worker postgres valkey)
```

Dùng output này để ghi thời điểm chạy, image/service đang active và CPU/RAM vào nhật ký kiểm thử.

## 3. Meeting, transcript và analysis API

Danh sách meeting gần nhất:

```bash
curl --fail --silent --show-error \
  -H "X-App-User-Id: ${APP_USER_ID}" \
  "${API_BASE}/v1/meetings?limit=20"
```

Trạng thái một meeting:

```bash
curl --fail --silent --show-error \
  -H "X-App-User-Id: ${APP_USER_ID}" \
  "${API_BASE}/v1/meetings/${MEETING_ID}"
```

Đồng bộ transcript rồi kiểm technical output. Chỉ chạy/lưu output này khi đã có consent; không dùng raw transcript làm ảnh hoặc trích dẫn trong khóa luận.

```bash
curl --fail --show-error -X POST \
  -H "X-App-User-Id: ${APP_USER_ID}" \
  "${API_BASE}/v1/meetings/${MEETING_ID}/sync"

curl --fail --silent --show-error \
  -H "X-App-User-Id: ${APP_USER_ID}" \
  "${API_BASE}/v1/meetings/${MEETING_ID}/transcript"
```

Các endpoint an toàn hơn cho report, không trả transcript text:

```bash
curl --fail --silent --show-error \
  -H "X-App-User-Id: ${APP_USER_ID}" \
  "${API_BASE}/v1/meetings/${MEETING_ID}/analysis"

curl --fail --silent --show-error \
  -H "X-App-User-Id: ${APP_USER_ID}" \
  "${API_BASE}/v1/meetings/${MEETING_ID}/analytics/overview"

curl --fail --silent --show-error \
  -H "X-App-User-Id: ${APP_USER_ID}" \
  "${API_BASE}/v1/meetings/${MEETING_ID}/analytics/evidence-manifest"
```

Kiểm tra Dashboard theo metadata đã redaction:

```bash
./scripts/dashboard-acceptance.sh "${MEETING_ID}"
```

## 4. Logs theo component

Application:

```bash
docker compose --env-file settings.env logs \
  --timestamps --since 30m --tail 300 backend worker
```

Database, queue và Dashboard:

```bash
docker compose --env-file settings.env logs \
  --timestamps --since 30m --tail 150 postgres valkey dashboard
```

Vexa meeting bot/transcript path:

```bash
(
  cd vexa/deploy/meetings-only &&
  COMPOSE_PROJECT_NAME=vexa-meetings \
  docker compose --env-file ../../../settings.env -f compose.yaml logs \
    --timestamps --since 30m --tail 300 gateway meeting-api runtime
)
```

## 5. PostgreSQL: thống kê không có transcript text

Mở `psql` mà không cần in password:

```bash
POSTGRES_DB="$(awk -F= '$1 == "POSTGRES_DB" { print $2; exit }' settings.env)"
POSTGRES_USER="$(awk -F= '$1 == "POSTGRES_USER" { print $2; exit }' settings.env)"

docker compose --env-file settings.env exec -T postgres \
  psql -X -U "${POSTGRES_USER:-meeting}" -d "${POSTGRES_DB:-meeting}" -P pager=off
```

Trong `psql`, thay placeholder UUID trước khi chạy truy vấn.

```sql
-- Meeting và transcript revision, không có native room URL hay transcript text.
SELECT id, platform, status, transcript_revision, created_at, started_at, ended_at, finalized_at
FROM meetings
ORDER BY created_at DESC
LIMIT 20;
```

```sql
-- Quy mô transcript của một meeting.
SELECT
  m.id AS meeting_id,
  m.status,
  m.transcript_revision,
  COUNT(s.id) AS total_segments,
  COUNT(s.id) FILTER (WHERE s.is_final) AS final_segments,
  COUNT(s.id) FILTER (WHERE s.retracted) AS retracted_segments,
  COUNT(DISTINCT s.language) AS language_count
FROM meetings m
LEFT JOIN transcript_segments s ON s.meeting_id = m.id
WHERE m.id = '<MEETING_ID>'::uuid
GROUP BY m.id, m.status, m.transcript_revision;
```

```sql
-- Run/model/revision/metrics của một meeting.
SELECT
  id AS run_id,
  kind,
  status,
  source_revision,
  model_version,
  preprocessing_version,
  input_segment_count,
  attempt,
  error_code,
  created_at,
  finished_at,
  metrics
FROM analysis_runs
WHERE meeting_id = '<MEETING_ID>'::uuid
ORDER BY created_at DESC;
```

```sql
-- Nhãn, confidence và inference time của một run.
SELECT
  COALESCE(sp.label, 'unknown') AS label,
  COUNT(*) AS unit_count,
  ROUND(AVG(sp.confidence)::numeric, 3) AS avg_confidence,
  ROUND(AVG(sp.inference_ms)::numeric, 1) AS avg_inference_ms
FROM analysis_units au
LEFT JOIN sentiment_predictions sp
  ON sp.analysis_unit_id = au.id
 AND sp.analysis_run_id = au.analysis_run_id
WHERE au.analysis_run_id = '<RUN_ID>'::uuid
GROUP BY COALESCE(sp.label, 'unknown')
ORDER BY unit_count DESC;
```

```sql
-- Dữ liệu bị quality gate loại, theo status và language.
SELECT quality_status, language, COUNT(*) AS unit_count
FROM analysis_units
WHERE analysis_run_id = '<RUN_ID>'::uuid
GROUP BY quality_status, language
ORDER BY unit_count DESC;
```

## 6. Valkey queue

```bash
docker compose --env-file settings.env exec -T valkey \
  valkey-cli --raw XLEN ai.analysis.jobs

docker compose --env-file settings.env exec -T valkey \
  valkey-cli --raw XINFO GROUPS ai.analysis.jobs
```

`XLEN` và consumer-group state giúp xác định job có bị kẹt trong queue không. Không xóa stream hoặc ACK message bằng lệnh tay khi đang thực nghiệm.

## 7. Evidence redaction-safe

Lưu metadata/report output ở local:

```bash
EVIDENCE_DIR="evidence/uat/${MEETING_ID}"
mkdir -p "${EVIDENCE_DIR}"

./scripts/runtime-status.sh > "${EVIDENCE_DIR}/runtime-status.txt"
docker compose --env-file settings.env ps > "${EVIDENCE_DIR}/compose-ps.txt"

curl --fail --silent --show-error \
  -H "X-App-User-Id: ${APP_USER_ID}" \
  "${API_BASE}/v1/meetings/${MEETING_ID}/analytics/overview" \
  > "${EVIDENCE_DIR}/analytics-overview.json"

curl --fail --silent --show-error \
  -H "X-App-User-Id: ${APP_USER_ID}" \
  "${API_BASE}/v1/meetings/${MEETING_ID}/analytics/evidence-manifest" \
  > "${EVIDENCE_DIR}/evidence-manifest.json"
```

Chỉ đưa các chỉ số tổng hợp sau vào workbook/khóa luận: trạng thái bot, số segment final, số segment hợp lệ/nhiễu, run ID, model/preprocessing version, revision, coverage, inference time, và kết luận `PASS`/`FAIL`/`BLOCKED`/`NOISE`.
