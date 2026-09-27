# Runbook build hệ thống và bước tiếp theo của khóa luận

> Mục tiêu: dựng và kiểm chứng luồng Google Meet → Vexa → transcript → backend → analysis worker → dashboard.  
> MVP dùng Google Meet + Vexa; `baseline-rules-v1` chỉ để kiểm chứng pipeline, không phải PhoBERT.

## 1. Điều kiện hoàn thành build

- Vexa Gateway, backend, worker, PostgreSQL, Valkey và dashboard hoạt động.
- Backend gọi Vexa qua Docker network `vexa-meetings_vexa`.
- Tạo bot cho một Google Meet, sync được transcript finalized.
- Final analysis hoàn thành; dashboard hiện KPI, timeline và evidence theo application UUID.

Không thực hiện fine-tune PhoBERT hoặc tích hợp Zoom/Teams/Jitsi trước khi đạt bốn điều kiện này.

## 2. Chuẩn bị Docker và cấu hình chung

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
docker info
docker compose version
chmod 600 settings.env
chmod 755 scripts/vexa-selfhost.sh scripts/generate-selfhost-secrets.sh
./scripts/vexa-selfhost.sh import-legacy-config
```

`settings.env` là file runtime duy nhất cho application và Vexa. Không commit file này.

Mở `settings.env` và điền giá trị thật (không rỗng, không `CHANGE_ME`) cho:

```dotenv
POSTGRES_PASSWORD=
VEXA_WEBHOOK_SECRET=
DB_PASSWORD=
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
ADMIN_TOKEN=
INTERNAL_API_SECRET=
```

Nếu chưa có secret, chạy `./scripts/generate-selfhost-secrets.sh`, rồi copy output vào đúng key. `POSTGRES_PASSWORD` và `DB_PASSWORD` phải khác nhau. Xóa dòng `POSTGRES_PASSWORD` bị trùng, chỉ giữ một dòng đúng với database ứng dụng.

Kiểm tra cấu hình Vexa:

```bash
./scripts/vexa-selfhost.sh check
```

**Pass:** hiện `Configuration is valid.` Đồng thời bảo đảm:

- `VEXA_COMPOSE_PROJECT_NAME=vexa-meetings` (không thêm `COMPOSE_PROJECT_NAME` vào `settings.env`).
- `VEXA_NETWORK=vexa-meetings_vexa`
- `VEXA_API_BASE=http://gateway:8000`
- `VEXA_API_KEY=` vẫn để trống cho đến Bước 4.

## 3. Build transcription service

Vexa vẫn khởi động khi chưa có STT, nhưng bot sẽ trả `503` nếu transcription bật. Cấu hình `source/vexa/deploy/transcription/.env`:

```dotenv
API_TOKEN=replace_with_a_new_stt_token
TRANSCRIPTION_LB_PORT=8083
MODEL_SIZE=small
```

Build bản CPU cho smoke test:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source/vexa/deploy/transcription
docker compose -f docker-compose.cpu.yml up -d --build
curl --fail http://127.0.0.1:8083/health
```

Sau đó đặt trong `source/settings.env`:

```dotenv
TRANSCRIPTION_SERVICE_URL=http://192.168.1.10:8083
TRANSCRIPTION_SERVICE_TOKEN=copy_the_API_TOKEN_value_here
TRANSCRIPTION_MODEL=
```

Không dùng `127.0.0.1` cho `TRANSCRIPTION_SERVICE_URL`; từ container `meeting-api`, địa chỉ này không trỏ tới Docker host. Dùng IP LAN của host hoặc một network Docker dùng chung.

Khi STT chạy trên cùng máy, có thể đồng bộ URL/token mà không in token ra terminal:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
HOST_LAN_IP=192.168.1.239 ./scripts/vexa-selfhost.sh sync-transcription-config
```

**Pass:** `./scripts/vexa-selfhost.sh check` không còn cảnh báo transcription.

## 4. Build Vexa và tạo API key

Nếu `admin-api` từng báo `password authentication failed for user "postgres"`, cần chọn một trong hai cách:

1. Cần giữ dữ liệu: khôi phục chính xác `DB_PASSWORD` đã dùng lúc khởi tạo volume.
2. Cài development mới, không cần dữ liệu Vexa: reset riêng Vexa rồi dựng lại.

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source/vexa/deploy/meetings-only
docker compose --env-file ../../../settings.env -f compose.yaml down -v
```

`down -v` xóa PostgreSQL, Redis, MinIO và token của Vexa. Không chạy nếu cần giữ dữ liệu.

Build và kiểm tra Vexa:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh status
./scripts/vexa-selfhost.sh verify
```

**Pass:** Gateway health pass; `admin-api`, `meeting-api`, `runtime`, `postgres`, `redis`, `minio` running/healthy.

Tạo token có scope `bot,tx`:

```bash
./scripts/vexa-selfhost.sh mint-token
```

Copy token `vxa_...` được in ra vào đúng một dòng trong `settings.env`:

```dotenv
VEXA_API_KEY=vxa_...
```

Không đưa token vào Git hoặc log.

## 5. Build ứng dụng Meeting Intelligence

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
docker compose --env-file settings.env config --quiet
docker compose --env-file settings.env up -d --build
docker compose --env-file settings.env ps
./scripts/verify.sh
```

**Pass:** `backend`, PostgreSQL và Valkey healthy; `worker` running; `/ready` và dashboard trả HTTP 200.

URL sử dụng giá trị trong `settings.env`:

```text
Backend:   http://127.0.0.1:<API_PORT>
Dashboard: http://127.0.0.1:<DASHBOARD_PORT>
```

Nếu dashboard lỗi `502`:

```bash
docker compose --env-file settings.env logs --tail=120 backend worker dashboard
```

## 6. Smoke test Google Meet → transcript → analysis

### 6.1 Tạo meeting

```bash
curl --fail --show-error \
  -X POST http://127.0.0.1:<API_PORT>/v1/meetings \
  -H 'Content-Type: application/json' \
  -H 'X-App-User-Id: local-dev' \
  -d '{"meeting_url":"https://meet.google.com/abc-defg-hij","bot_name":"Meeting Assistant"}'
```

Lưu `id` UUID trả về thành `<MEETING_ID>`. Đây là application UUID, không phải room code Google Meet. Admit bot và nói thử vài câu tiếng Việt.

### 6.2 Sync transcript

```bash
curl --fail --show-error \
  -X POST http://127.0.0.1:<API_PORT>/v1/meetings/<MEETING_ID>/sync \
  -H 'X-App-User-Id: local-dev'

curl --fail --show-error \
  http://127.0.0.1:<API_PORT>/v1/meetings/<MEETING_ID>/transcript \
  -H 'X-App-User-Id: local-dev'
```

**Pass:** có ít nhất một segment `is_final=true`. Transcript rỗng thường là lỗi capture/STT upstream, không phải dashboard/model.

### 6.3 Chạy final analysis và dashboard

```bash
curl --fail --show-error \
  -X POST 'http://127.0.0.1:<API_PORT>/v1/meetings/<MEETING_ID>/analysis?kind=final' \
  -H 'X-App-User-Id: local-dev'

curl --fail --show-error \
  http://127.0.0.1:<API_PORT>/v1/meetings/<MEETING_ID>/analytics/overview \
  -H 'X-App-User-Id: local-dev'
```

Mở dashboard, nhập `<MEETING_ID>`, rồi kiểm tra KPI, timeline, coverage, `unknown`, evidence và model version.

**Pass:** final run `succeeded`; evidence có thể truy về transcript/timestamp. `unknown` là kết quả hợp lệ của quality gate.

## 7. Test trước demo và bằng chứng luận văn

1. [ ] Restart worker; retry/final analysis không mất job hay tạo prediction trùng.
2. [ ] Sync lặp không tạo segment trùng.
3. [ ] UUID sai ở dashboard hiển thị lỗi rõ ràng, không trắng trang.
4. [ ] SSE reconnect không render trùng event.
5. [ ] Transcript ngắn/lặp/code-switch/draft/retract có `unknown` hoặc quality reason đúng policy.
6. [ ] Log không chứa API key, password, raw transcript hay PII.

Lưu ảnh/log đã che secret: trạng thái Compose, Gateway/`/ready`, tạo meeting, sync transcript, final analysis, dashboard evidence, kết quả test và môi trường đo (CPU/GPU/RAM/version/cỡ mẫu).

## 8. Việc làm sau khi build pass

1. Hoàn thiện migration, idempotency, revision/retract và repository tests.
2. Hoàn thiện dashboard: empty/loading/error state, SSE reconnect, evidence và phân quyền.
3. Thêm monitoring queue/error, health check và runbook sự cố.
4. Cập nhật ERD, architecture/sequence diagram và chương implementation trong luận văn.
5. Chỉ bắt đầu annotation + benchmark/fine-tune PhoBERT khi có consent và tập nhãn split theo meeting.

Tham khảo cấu hình chi tiết tại [`source/SELFHOST_CONFIGURATION.md`](source/SELFHOST_CONFIGURATION.md) và backlog kỹ thuật tại [`THESIS_IMPLEMENTATION_TASK_BREAKDOWN.md`](THESIS_IMPLEMENTATION_TASK_BREAKDOWN.md).
