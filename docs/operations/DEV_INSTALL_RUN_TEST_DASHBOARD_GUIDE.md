# Hướng dẫn DEV duy nhất: Cài đặt → Chạy → Test → Dashboard

> Mục tiêu: dựng toàn bộ Meeting Intelligence trên môi trường DEV bằng Terminal
> và Docker Compose, kiểm tra pipeline, chạy Google Meet có consent và xem kết quả
> tự động trên Dashboard.
>
> Source chạy chính: `source/compose.yaml`, `source/src/backend`,
> `source/src/dashboard`. Không dùng `source/meeting-intelligence-backend/` vì đó
> là bản legacy.

## 0. Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

```text
Google Meet → Vexa bot → transcription → PostgreSQL → worker AI → Dashboard
```

và có tất cả kết quả sau:

- Backend `/ready` trả `200`.
- Vexa gateway và transcription `/health` trả `200`.
- Google Meet có bot được admit, transcript vào application DB.
- Final analysis có trạng thái `succeeded`.
- Refresh Dashboard tự chọn meeting mới nhất, hiển thị transcript/KPI/evidence.

## 1. Điều kiện máy DEV

Máy cần Docker Engine, Docker Compose v2, `curl` và quyền chạy Docker.

```bash
docker info
docker compose version
curl --version
```

Nếu dùng STT GPU, cần NVIDIA Container Toolkit. Nếu không có GPU, dùng transcription
CPU; sẽ chậm hơn nên cần đợi 35–45 giây sau khi nói.

## 2. Vào đúng thư mục và tạo runtime config

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/bootstrap.sh
chmod 600 settings.env
```

`settings.env` chứa secret local, không commit hoặc gửi lên chat. Nếu file này đã
tồn tại, `bootstrap.sh` không ghi đè.

Kiểm tra các key có mặt mà không in secret:

```bash
cut -d= -f1 settings.env | sed '/^[[:space:]]*#/d;/^[[:space:]]*$/d' | sort
```

Các giá trị bắt buộc không được để `CHANGE_ME`/rỗng:

```text
POSTGRES_PASSWORD              DB_PASSWORD
MINIO_ACCESS_KEY               MINIO_SECRET_KEY
ADMIN_TOKEN                    INTERNAL_API_SECRET
VEXA_WEBHOOK_SECRET            VEXA_API_KEY
TRANSCRIPTION_SERVICE_URL      TRANSCRIPTION_SERVICE_TOKEN
```

`POSTGRES_PASSWORD` và `DB_PASSWORD` phải khác nhau. Kiểm tra port Vexa là số,
đặc biệt:

```dotenv
RUNTIME_API_PORT=18190
```

Không để `18190z` hoặc ký tự thừa, vì Docker sẽ báo `invalid hostPort`.

## 3. Dựng transcription (STT)

Transcription là điều kiện bắt buộc để có transcript. Nếu chạy STT ngay máy DEV:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source/vexa/deploy/transcription

# Máy không có GPU:
docker compose -f docker-compose.cpu.yml up -d --build

# Máy có NVIDIA GPU thì dùng thay lệnh trên:
# docker compose up -d --build

curl --fail --show-error http://127.0.0.1:8083/health
```

Quay lại `source`, đồng bộ URL/token STT vào runtime config bằng LAN IP của máy STT
(không dùng `127.0.0.1` trong Vexa container):

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
HOST_LAN_IP=<IP-LAN-may-STT> ./scripts/vexa-selfhost.sh sync-transcription-config

STT_URL=$(awk -F= '$1 == "TRANSCRIPTION_SERVICE_URL" { print $2; exit }' settings.env)
curl --fail --show-error --max-time 5 "$STT_URL/health"
```

**Pass:** health trả HTTP 200. Nếu fail, không chuyển sang bước Google Meet.

## 4. Dựng Vexa meetings-only

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/vexa-selfhost.sh check
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
./scripts/vexa-selfhost.sh status
```

`verify` cũng kiểm tra image runner được runtime tạo theo từng meeting. Nếu báo
thiếu image, tải đúng image được cấu hình (image này có dung lượng vài GB):

```bash
BROWSER_IMAGE=$(awk -F= '$1 == "BROWSER_IMAGE" { print $2; exit }' settings.env)
BROWSER_IMAGE=${BROWSER_IMAGE:-vexaai/vexa-bot:v012}
docker pull "$BROWSER_IMAGE"
./scripts/vexa-selfhost.sh verify
```

Nếu chưa có `VEXA_API_KEY`, tạo token rồi dán giá trị `vxa_...` vào `settings.env`:

```bash
./scripts/vexa-selfhost.sh mint-token
```

Sau khi sửa `settings.env`, chạy lại:

```bash
./scripts/vexa-selfhost.sh start
```

## 5. Build và chạy application

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
docker compose --env-file settings.env config --quiet
docker compose --env-file settings.env up -d --build
docker compose --env-file settings.env ps
```

Đồng bộ password database cho backend/worker (an toàn, không xóa dữ liệu):

```bash
./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker
```

Lấy URL runtime từ config, không đoán port `8088`/`3000` vì có thể trùng legacy:

```bash
API_PORT=$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env)
API_PORT=${API_PORT:-8088}
API_BASE="http://127.0.0.1:${API_PORT}"

DASHBOARD_PORT=$(awk -F= '$1 == "DASHBOARD_PORT" { print $2; exit }' settings.env)
DASHBOARD_PORT=${DASHBOARD_PORT:-3000}
DASHBOARD_URL="http://127.0.0.1:${DASHBOARD_PORT}"

echo "API:       ${API_BASE}"
echo "Dashboard: ${DASHBOARD_URL}"
```

## 6. Test sức khỏe sau build

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/runtime-status.sh
./scripts/verify.sh
curl --fail --show-error "${API_BASE}/ready"
curl --fail --show-error "${DASHBOARD_URL}/"
docker compose --env-file settings.env logs --since=2m --tail=80 worker
```

**Pass:** backend/dashboard trả HTTP 200; PostgreSQL/Valkey healthy; log mới worker
không có `InvalidPasswordError`.

Nếu worker có `InvalidPasswordError`, chạy lại Bước 5 (sync password + restart).
Không dựa vào `logs --tail=30` vì có thể là traceback cũ trước restart.

## 7. Test synthetic bắt buộc trước dữ liệu thật

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/smoke-analysis-pipeline.sh
```

**Pass:**

```text
PASS: synthetic fixture completed API -> queue -> worker -> analytics API.
```

Script tự tạo và xóa fixture; không có Google Meet hoặc transcript thật trong test này.

## 8. Test Google Meet E2E

1. Tạo Google Meet test và lấy consent người tham gia.
2. Sao chép URL Meet đầy đủ. Backend chấp nhận cả dạng trực tiếp
   `https://meet.google.com/abc-defg-hij` lẫn URL có tiền tố
   `https://meet.google.com/meet/abc-defg-hij`; không dán cú pháp Markdown `[link](...)`.
3. Tạo bot qua backend:

```bash
MEET_URL='https://meet.google.com/abc-defg-hij'

curl --fail --silent --show-error \
  -X POST "${API_BASE}/v1/meetings" \
  -H 'Content-Type: application/json' \
  -H 'X-App-User-Id: local-dev' \
  -d "{\"meeting_url\":\"${MEET_URL}\",\"bot_name\":\"Meeting Assistant\"}"
```

4. Sao chép `id` UUID trong response, lưu ở dòng riêng trong cùng terminal:

```bash
MEETING_ID='<UUID-do-backend-tra-ve>'
```

5. Vào Google Meet, admit bot. Bật mic của người tham gia thật, nói rõ liên tục
15–20 giây, dừng nói, rồi chờ 35–45 giây nếu STT dùng CPU.
6. Sync transcript:

```bash
curl --fail --silent --show-error \
  -X POST "${API_BASE}/v1/meetings/${MEETING_ID}/sync" \
  -H 'X-App-User-Id: local-dev'

curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${API_BASE}/v1/meetings/${MEETING_ID}/transcript"
```

**Pass:** sync có `changed > 0`, `total > 0`; transcript có segment `is_final=true`.

Nếu `total=0`:

```bash
docker ps --format '{{.Names}}' | grep '^vexa-mtg-'
docker logs --tail=150 <ten-container-vexa-mtg>
```

- `AUDIO ... emitted=...`: bot đã nhận audio; tiếp tục chờ STT.
- `silent`/`emitted=0`: kiểm admit, mic và nói lại.
- `STT DEGRADED`, `STT-FAULT`, `401`, `400`, `fetch failed`: quay lại Bước 3.

## 9. Chạy final analysis

Chỉ chạy sau khi Bước 8 có transcript:

```bash
curl --fail --silent --show-error \
  -X POST "${API_BASE}/v1/meetings/${MEETING_ID}/analysis?kind=final" \
  -H 'X-App-User-Id: local-dev'
```

Theo dõi trạng thái:

```bash
while true; do
  curl --fail --silent --show-error \
    -H 'X-App-User-Id: local-dev' \
    "${API_BASE}/v1/meetings/${MEETING_ID}/analysis"
  sleep 2
done
```

Nhấn `Ctrl+C` khi run mới nhất có `"status":"succeeded"`.

## 10. Mở Dashboard và kiểm chứng kết quả

Mở URL đã in ở Bước 5. Dashboard tự chọn meeting mới nhất, tự tải transcript và
tự refresh khi backend có event mới. Không cần nhập UUID trong luồng bình thường.

Chỉ nhập UUID vào ô khi muốn xem meeting cũ. Trên Dashboard kiểm tra:

| Thành phần | Kết quả cần có |
| --- | --- |
| Transcript trực tiếp | Có segment/text vừa nói |
| Status | `Analysis succeeded` khi final run xong |
| Model | `baseline-rules-v1` hoặc đúng `MODEL_VERSION` |
| KPI | Positive, Neutral, Negative, Coverage, Polarity |
| Timeline | Cửa sổ sentiment theo thời gian |
| Evidence | Text, speaker, label, confidence, timestamp |

Đối chiếu Dashboard với API:

```bash
curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${API_BASE}/v1/meetings/${MEETING_ID}/analytics/overview"
```

Nếu Dashboard báo `API 502` nhưng API `/ready` trả 200, Nginx Dashboard đang giữ
IP Docker cũ sau khi backend recreate. Sửa bằng:

```bash
docker compose --env-file settings.env restart dashboard
```

## 11. Kiểm tra database và model

`baseline-rules-v1` là baseline deterministic để chứng minh pipeline; không phải
PhoBERT và không được dùng để tuyên bố accuracy mô hình.

```bash
grep '^MODEL_VERSION=' settings.env

docker compose --env-file settings.env exec -T postgres \
  psql -U meeting -d meeting -P pager=off \
  -c "SELECT kind, source_revision, model_version, status, metrics, error_code FROM analysis_runs WHERE meeting_id = '${MEETING_ID}'::uuid ORDER BY created_at DESC;"

docker compose --env-file settings.env exec -T postgres \
  psql -U meeting -d meeting -P pager=off \
  -c "SELECT speaker_name, language, is_final, left(text, 120) AS text_preview FROM transcript_segments WHERE meeting_id = '${MEETING_ID}'::uuid ORDER BY start_seconds;"
```

## 12. Dừng/restart an toàn

Dừng application nhưng giữ database/queue:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
docker compose --env-file settings.env down
```

Khởi động lại:

```bash
./scripts/vexa-selfhost.sh start
docker compose --env-file settings.env up -d
./scripts/verify.sh
```

Không chạy `docker compose down -v`, `docker volume rm` hoặc reset database nếu
chưa có backup và xác nhận rõ ràng.

## 13. Checklist DEV cuối

| Hạng mục | Pass/Fail |
| --- | --- |
| Docker/Compose sẵn sàng | ☐ / ☐ |
| `settings.env` đủ secret, quyền 600 | ☐ / ☐ |
| Vexa + transcription health | ☐ / ☐ |
| Backend/worker/PostgreSQL/Valkey/Dashboard chạy | ☐ / ☐ |
| Synthetic smoke pass | ☐ / ☐ |
| Google Meet transcript `total > 0` | ☐ / ☐ |
| Final analysis `succeeded` | ☐ / ☐ |
| Dashboard khớp transcript/API/model | ☐ / ☐ |
| Evidence không lộ secret/PII | ☐ / ☐ |
