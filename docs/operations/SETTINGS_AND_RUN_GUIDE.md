# Hướng dẫn build và chạy Meeting Intelligence từng bước

> Đây là runbook cài đặt hiện hành. Làm lần lượt từ Bước 0 đến Bước 8 và chỉ chuyển bước khi checkpoint của bước trước đã đạt. Đường demo/UAT hiện hành là **Jitsi Meet → Vexa → STT local → FastAPI → PostgreSQL/Valkey → Dashboard**.

## Kết quả cần đạt

Sau khi hoàn thành, máy local có các thành phần sau:

```text
Jitsi Meet
  → Vexa meeting bot
  → local transcription service
  → FastAPI + PostgreSQL + Valkey + sentiment worker
  → Dashboard tại http://127.0.0.1:<DASHBOARD_PORT>
```

Các điều kiện đạt tối thiểu là:

- `/ready` của backend trả HTTP `200`.
- Vexa gateway và transcription service healthy.
- Smoke test synthetic in `PASS`.
- Dashboard mở được.
- Khi test Jitsi có consent, bot vào phòng, transcript final xuất hiện và final analysis có trạng thái `succeeded`.

Google Meet chỉ còn tương thích cho run lịch sử; không dùng nó làm đường build hoặc nghiệm thu chính vì guest bot có thể bị chặn ở admission.

## Bước 0 — Kiểm tra máy và vào đúng thư mục

Máy cần Docker Engine, Docker Compose v2, `curl` và quyền dùng Docker. Python, PostgreSQL, Valkey và Nginx được chạy trong container, không cần cài riêng trên host.

```bash
docker info >/dev/null && echo "PASS: Docker Engine"
docker compose version
curl --version

cd /home/lamsd/Documents/Buildkhoaluan/source
pwd
```

**Checkpoint:** `pwd` phải kết thúc bằng `/Buildkhoaluan/source`. Nếu Docker chưa chạy, khởi động Docker trước khi tiếp tục.

## Bước 1 — Tạo cấu hình local và secret

`settings.env` là file cấu hình duy nhất cho application và Vexa. File này chứa secret, không được commit, gửi qua chat hoặc chụp vào ảnh evidence.

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
chmod 755 scripts/bootstrap.sh scripts/generate-selfhost-secrets.sh \
  scripts/vexa-selfhost.sh scripts/runtime-settings.sh

./scripts/bootstrap.sh
chmod 600 settings.env
```

Nếu `settings.env` đã tồn tại, `bootstrap.sh` sẽ không ghi đè nó.

Tạo các secret mới trong terminal local:

```bash
./scripts/generate-selfhost-secrets.sh
```

Mở `settings.env` trong editor local và điền các giá trị script vừa in vào đúng biến:

```text
POSTGRES_PASSWORD
DB_PASSWORD
MINIO_ACCESS_KEY
MINIO_SECRET_KEY
ADMIN_TOKEN
INTERNAL_API_SECRET
VEXA_WEBHOOK_SECRET
```

Giữ giá trị mặc định sau nếu không có lý do thay đổi:

```dotenv
VEXA_MODE=self_host
VEXA_API_BASE=http://gateway:8000
VEXA_NETWORK=vexa-meetings_vexa
CLASSIFIER_ADAPTER=rules
MODEL_VERSION=baseline-rules-v3
PREPROCESSING_VERSION=2026-11-stt-quality-gate-v2
```

Không điền `VEXA_API_KEY` ở bước này; token chỉ được tạo sau khi Vexa đã chạy.

Kiểm tra tên biến mà không in secret:

```bash
cut -d= -f1 settings.env | sed '/^[[:space:]]*#/d;/^[[:space:]]*$/d' | sort
```

**Checkpoint:** không còn giá trị `CHANGE_ME` trong các secret ở trên. `POSTGRES_PASSWORD` và `DB_PASSWORD` phải khác nhau.

## Bước 2 — Build transcription service (STT)

STT là thành phần bắt buộc để bot tạo transcript. Với máy không có NVIDIA GPU, dùng bản CPU; `MODEL_SIZE=small` là lựa chọn an toàn cho demo realtime.

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source/vexa/deploy/transcription

[ -f .env ] || cp ".env copy.example" .env
chmod 600 .env
```

Mở file `source/vexa/deploy/transcription/.env` và tối thiểu kiểm tra/chỉnh:

```dotenv
MODEL_SIZE=small
COMPUTE_TYPE=int8
API_TOKEN=<mot-secret-rieng-cho-STT>
```

Tạo `API_TOKEN` bằng `openssl rand -hex 32` nếu chưa có. Không dùng lại password database hoặc Vexa token cho giá trị này.

Máy CPU:

```bash
docker compose -f docker-compose.cpu.yml up -d --build
docker compose -f docker-compose.cpu.yml ps
curl --fail --show-error http://127.0.0.1:8083/health
```

Máy có NVIDIA Container Toolkit có thể dùng GPU:

```bash
docker compose up -d --build
docker compose ps
curl --fail --show-error http://127.0.0.1:8083/health
```

Đồng bộ URL/token của STT vào `settings.env`. Vexa chạy trong container, do đó không dùng `127.0.0.1` làm URL STT.

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source

./scripts/vexa-selfhost.sh sync-transcription-config
```

Nếu script không tự tìm đúng IP LAN, chạy lại với giá trị thực, ví dụ:

```bash
HOST_LAN_IP=192.168.1.20 ./scripts/vexa-selfhost.sh sync-transcription-config
```

**Checkpoint:** health STT trả HTTP `200`, và `settings.env` có `TRANSCRIPTION_SERVICE_URL` cùng `TRANSCRIPTION_SERVICE_TOKEN` nhưng không in các giá trị đó ra terminal.

## Bước 3 — Build Vexa meetings-only và tạo API key

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source

./scripts/vexa-selfhost.sh check
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
./scripts/vexa-selfhost.sh status
```

Nếu `verify` báo thiếu image bot runner, chạy đúng lệnh `docker pull ...` mà script in ra, sau đó chạy lại `verify`.

Tạo Vexa API key một lần:

```bash
./scripts/vexa-selfhost.sh mint-token
```

Token `vxa_...` chỉ hiện một lần. Ngay sau đó, lưu bằng input ẩn:

```bash
./scripts/runtime-settings.sh configure-vexa
```

Chọn cấu hình model hiện tại bằng terminal wizard. Với demo đầu tiên, giữ `rules` và `baseline-rules-v3`.

```bash
./scripts/runtime-settings.sh configure-model
./scripts/runtime-settings.sh status
```

**Checkpoint:** `vexa-selfhost.sh verify` pass; `runtime-settings.sh status` báo `VEXA_API_KEY configured`. Lệnh status không in token.

## Bước 4 — Build application stack

Không dùng `docker compose restart` sau khi sửa `settings.env`, vì restart không đọc lại `env_file`. Dùng đúng script sau:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source

./scripts/runtime-settings.sh apply
docker compose --env-file settings.env ps
```

Lấy URL runtime từ cấu hình thay vì đoán port:

```bash
API_PORT="$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env)"
API_PORT="${API_PORT:-8088}"

DASHBOARD_PORT="$(awk -F= '$1 == "DASHBOARD_PORT" { print $2; exit }' settings.env)"
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"

echo "API:       http://127.0.0.1:${API_PORT}"
echo "Dashboard: http://127.0.0.1:${DASHBOARD_PORT}/"
```

**Checkpoint:** service `backend`, `worker`, `postgres`, `valkey`, `dashboard` và `operator-runner` có trạng thái running/healthy theo Compose.

### Khi gặp lỗi password PostgreSQL

Chỉ chạy phần này nếu log backend/worker có `InvalidPasswordError` hoặc bạn đã đổi `POSTGRES_PASSWORD` sau khi volume database được tạo:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker
```

Lệnh này chỉ cập nhật password của role ứng dụng; không xóa database hay volume.

## Bước 5 — Health check và smoke test không dùng dữ liệu thật

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source

./scripts/runtime-status.sh
./scripts/verify.sh
./scripts/vexa-selfhost.sh verify
./scripts/smoke-analysis-pipeline.sh
```

**Checkpoint:**

```text
Verified: backend health and Dashboard are reachable.
PASS: synthetic fixture completed API -> queue -> worker -> analytics API.
```

Smoke test chỉ dùng fixture tổng hợp và tự cleanup. Nếu smoke test chưa pass, không chuyển sang Jitsi thật.

## Bước 6 — Mở Dashboard và tạo bot Jitsi

1. Mở `http://127.0.0.1:<DASHBOARD_PORT>/` bằng URL ở Bước 4; hard refresh bằng `Ctrl+Shift+R`.
2. Tạo một phòng Jitsi mới, ví dụ `https://meet.jit.si/TenPhongKiemThuDuyNhat`, rồi giữ host trong phòng.
3. Nhận consent của mọi người trước khi bot xử lý audio hoặc transcript.
4. Trong Dashboard, dán URL Jitsi đầy đủ, chọn `Tiếng Việt` hoặc `auto`, nhập tên bot, tick consent rồi bấm **Yêu cầu bot tham gia**.
5. Lưu Application Meeting UUID mà Dashboard trả về. Không dùng tên phòng Jitsi thay cho UUID.
6. Chờ bot xuất hiện trong participant list. Không gửi request thứ hai khi trạng thái vẫn là `requested`, `joining` hoặc `active`.
7. Nói câu ngắn, rõ ràng, không bật nhạc/video nền. Chờ segment final xuất hiện.
8. Bấm **Chạy model đang cấu hình** sau khi đã có transcript final.

Khi cần chẩn đoán bằng API thay vì Dashboard:

```bash
curl --fail --show-error -X POST "http://127.0.0.1:${API_PORT}/v1/meetings" \
  -H 'Content-Type: application/json' \
  -H 'X-App-User-Id: local-dev' \
  -d '{"meeting_url":"https://meet.jit.si/TenPhongKiemThuDuyNhat","bot_name":"Meeting Assistant","transcription_language":"vi"}'
```

Chi tiết kiểm transcript, run analysis và lỗi bot xem [Checklist Jitsi E2E](JITSI_E2E_VERIFICATION_CHECKLIST.md).

## Bước 7 — Lấy số liệu cho Excel và khóa luận

Sau khi final analysis có trạng thái `succeeded`, chạy:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source

MEETING_ID='<APPLICATION_MEETING_UUID>'
./scripts/dashboard-acceptance.sh "${MEETING_ID}"
```

Lệnh chỉ in metadata phục vụ báo cáo: model/preprocessing version, revision, coverage và batch inference. Không tải raw transcript.

Để lấy data từ API, logs, PostgreSQL, Valkey và export evidence đã redaction, dùng [Hướng dẫn truy xuất dữ liệu và evidence](DATA_RETRIEVAL_AND_REPORTING.md). Ghi các số liệu vào workbook `Nhat_ky_kiem_thu_Jitsi_STT.xlsx`, đặc biệt: trạng thái bot, số segment, segment hợp lệ/nhiễu, run ID, coverage, độ trễ và kết luận `PASS`/`FAIL`/`BLOCKED`/`NOISE`.

## Bước 8 — Thu evidence và dừng stack an toàn

Tạo evidence cho smoke integration (không có transcript thật):

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/capture-evidence.sh integration EVID-YYYYMMDD-001
```

Khi chỉ cần dừng application nhưng giữ database/queue:

```bash
docker compose --env-file settings.env down
```

Không dùng `docker compose down -v` trong vận hành thông thường. Nó xóa PostgreSQL/Valkey named volumes và làm mất dữ liệu local.

## Xử lý lỗi theo triệu chứng

| Hiện tượng | Kiểm tra trước | Hướng xử lý an toàn |
| --- | --- | --- |
| `vexa-selfhost.sh check` fail | placeholder/biến thiếu trong `settings.env` | Sửa cấu hình, không recreate volume. |
| STT health không trả 200 | `docker compose -f docker-compose.cpu.yml ps` và logs transcription | Kiểm `.env`, port `8083`, model CPU `small`; sau đó sync lại URL/token. |
| Backend không ready | `docker compose ... logs --tail=150 backend worker` | Nếu có password error, chạy `sync-app-db-password.sh`; nếu không, lưu log đã redaction trước khi restart. |
| Bot không xuất hiện trong Jitsi | host còn trong phòng, URL Jitsi, `vexa-selfhost.sh status` | Kiểm policy/password/lobby phòng; không tạo request lặp liên tục. |
| Bot có mặt nhưng transcript rỗng | health STT, logs `gateway meeting-api runtime` | Kiểm audio vào bot và token/URL STT; không tạo transcript giả. |
| Transcript có nhưng KPI là 0 | endpoint analysis, log worker, quality reason | Chỉ chạy final analysis sau segment `is_final=true`; kiểm language/quality gate và revision. |
| Dashboard không cập nhật | `/ready`, `dashboard-acceptance.sh`, log dashboard/backend | Hard refresh; kiểm application UUID và SSE. |

Lệnh log an toàn cơ bản:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
docker compose --env-file settings.env logs --timestamps --tail=150 backend worker
./scripts/vexa-selfhost.sh status
```

Không đưa `settings.env`, Vexa API key, STT token, audio hoặc raw transcript vào Git, chat hay ảnh evidence công khai.
