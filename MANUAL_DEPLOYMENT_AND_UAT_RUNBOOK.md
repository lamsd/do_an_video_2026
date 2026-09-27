# Runbook deploy thủ công và chuẩn bị UAT

> Cập nhật: 27/09/2026  
> Mục tiêu: triển khai Meeting Intelligence bằng **Terminal + Docker Compose**,
> không dùng CI/CD ở giai đoạn hiện tại; kiểm chứng trước khi bàn giao UAT.

## 1. Phạm vi và quyết định triển khai

Đường deploy duy nhất hiện tại:

```text
Google Meet → Vexa + transcription → FastAPI → PostgreSQL / Valkey
                                          → sentiment worker → Dashboard
```

- Application: `source/compose.yaml`, `source/src/backend`, `source/src/dashboard`.
- Vexa: `source/vexa/deploy/meetings-only/compose.yaml`, được điều khiển qua
  `source/scripts/vexa-selfhost.sh`.
- Không dùng `source/meeting-intelligence-backend/`; đó là stack legacy.
- Không chạy `docker compose down -v` trong local/UAT; lệnh đó xóa volumes dữ liệu.
- Chưa có CI/CD. Mỗi release được build, kiểm tra và deploy thủ công theo tài liệu này.

## 2. Phân biệt các môi trường

| Môi trường | Mục đích | Cách chạy | Dữ liệu |
| --- | --- | --- | --- |
| Local dev | Phát triển và sửa lỗi | Docker Compose trên máy dev | Synthetic hoặc meeting có consent |
| UAT nội bộ | Người dùng/giảng viên kiểm thử acceptance | Docker Compose trên máy UAT riêng | Test data hoặc meeting có consent |
| Production | Chưa nằm trong phạm vi MVP | Chưa triển khai | Cần auth, TLS, backup/restore test |

UAT hiện là môi trường nội bộ. Dashboard chưa có JWT/session thật; không expose
Dashboard/API ra Internet. Giữ port bind `127.0.0.1` như `compose.yaml`, dùng SSH
tunnel hoặc reverse proxy có authentication khi cần người khác truy cập.

## 3. Chuẩn bị máy UAT (một lần)

### 3.1 Điều kiện máy

- Docker Engine hoạt động; Vexa self-host yêu cầu Docker Engine 26+.
- Docker Compose v2.
- Quyền chạy Docker cho user deploy.
- Đủ CPU/RAM/disk cho PostgreSQL, Vexa browser bot và transcription.
- Nếu transcription chạy máy riêng: UAT/Vexa phải truy cập được IP LAN của máy STT
  qua port `8083`.

Kiểm tra:

```bash
docker info
docker compose version
```

### 3.2 Lấy source và tạo file runtime

Trên máy UAT, lấy đúng source/release đã được kiểm tra. Tại thư mục dự án:

```bash
cd /path/to/Buildkhoaluan/source
./scripts/bootstrap.sh
chmod 600 settings.env
```

`settings.env` là file runtime riêng theo từng máy, không commit/copy lên chat.
Nếu đã có file UAT, **không** chạy lệnh copy ghi đè lên nó.

Các giá trị bắt buộc không được rỗng/`CHANGE_ME`:

```text
POSTGRES_PASSWORD
DB_PASSWORD
MINIO_ACCESS_KEY
MINIO_SECRET_KEY
ADMIN_TOKEN
INTERNAL_API_SECRET
VEXA_WEBHOOK_SECRET
VEXA_API_KEY
TRANSCRIPTION_SERVICE_URL
TRANSCRIPTION_SERVICE_TOKEN
```

Giữ hai password database khác nhau: `POSTGRES_PASSWORD` cho application và
`DB_PASSWORD` cho Vexa.

### 3.3 Port và network

Chọn port không xung đột với legacy/local stack. Ví dụ UAT:

```dotenv
API_PORT=8089
DASHBOARD_PORT=3001
VEXA_NETWORK=vexa-meetings_vexa
RUNTIME_API_PORT=18190
```

Tất cả host-port phải chỉ là số; `RUNTIME_API_PORT=18190z` là cấu hình sai và làm
Vexa Compose báo `invalid hostPort`.

## 4. Chuẩn bị transcription (bắt buộc trước E2E)

Transcription là service tách riêng. Vexa bot không tạo transcript nếu service
này không reachable.

Trên máy STT (GPU hoặc CPU), khởi động service nếu chưa chạy:

```bash
cd /path/to/Buildkhoaluan/source/vexa/deploy/transcription
# CPU cho UAT/dev:
docker compose -f docker-compose.cpu.yml up -d --build
# Hoặc GPU (NVIDIA Container Toolkit):
# docker compose up -d --build
curl --fail --show-error http://127.0.0.1:8083/health
```

Trên máy UAT/Vexa, cấu hình URL LAN thực tế, không dùng `127.0.0.1`:

```bash
cd /path/to/Buildkhoaluan/source
HOST_LAN_IP=<IP-LAN-cua-may-STT> ./scripts/vexa-selfhost.sh sync-transcription-config
./scripts/vexa-selfhost.sh check
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
```

Kiểm tra lần cuối từ máy UAT:

```bash
STT_URL=$(awk -F= '$1 == "TRANSCRIPTION_SERVICE_URL" { print $2; exit }' settings.env)
curl --fail --show-error --max-time 5 "$STT_URL/health"
```

**Pass:** health trả HTTP 200. `MODEL_SIZE`/model STT là model transcription; nó
khác model sentiment hiển thị trên Dashboard.

## 5. Backup trước deploy/update

Chỉ backup khi UAT đã có dữ liệu cần giữ. Tạo thư mục backup ngoài working tree,
chỉ người vận hành có quyền đọc:

```bash
cd /path/to/Buildkhoaluan/source
mkdir -p /srv/meeting-intelligence-backups
chmod 700 /srv/meeting-intelligence-backups

docker compose --env-file settings.env exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > /srv/meeting-intelligence-backups/app-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Không đặt backup trong Git. Vexa PostgreSQL/MinIO là domain riêng; cần backup riêng
nếu UAT phụ thuộc dữ liệu/token của Vexa.

## 6. Build và deploy thủ công application

Chạy toàn bộ trong thư mục `source`:

```bash
cd /path/to/Buildkhoaluan/source

docker compose --env-file settings.env config --quiet
docker compose --env-file settings.env up -d --build backend dashboard
docker compose --env-file settings.env up -d worker postgres valkey
```

Đồng bộ role password nếu deployment mới, sau khi đổi `POSTGRES_PASSWORD`, hoặc log
worker có `InvalidPasswordError`:

```bash
./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker
```

Không cần nhập `MEETING_ID` để Dashboard auto load: backend/Dashboard hiện tự lấy
meeting mới nhất của local user. Khi deploy source cũ chưa có tính năng này, build
lại cả `backend` và `dashboard` bằng lệnh ở trên.

## 7. Smoke check sau deploy

Lấy port từ config, không hard-code:

```bash
API_PORT=$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env)
API_PORT=${API_PORT:-8088}
DASHBOARD_PORT=$(awk -F= '$1 == "DASHBOARD_PORT" { print $2; exit }' settings.env)
DASHBOARD_PORT=${DASHBOARD_PORT:-3000}

./scripts/runtime-status.sh
./scripts/verify.sh
curl --fail --show-error "http://127.0.0.1:${API_PORT}/ready"
curl --fail --show-error "http://127.0.0.1:${DASHBOARD_PORT}/"
docker compose --env-file settings.env logs --since=2m --tail=80 worker
```

**Pass:** backend `/ready`, Dashboard HTTP 200, containers healthy/running và log
mới của worker không có `InvalidPasswordError`.

Chạy smoke pipeline không dùng dữ liệu thật:

```bash
./scripts/smoke-analysis-pipeline.sh
```

**Pass:** `PASS: synthetic fixture completed API -> queue -> worker -> analytics API.`

## 8. Xác nhận UAT Google Meet

Thực hiện theo [GOOGLE_MEET_E2E_VERIFICATION_CHECKLIST.md](GOOGLE_MEET_E2E_VERIFICATION_CHECKLIST.md).
Tóm tắt acceptance:

1. Tạo Google Meet test có consent và tạo bot qua backend.
2. Admit bot; nói rõ 15–20 giây; chờ 35–45 giây nếu STT chạy CPU.
3. Kiểm `sync` có `changed > 0`, `total > 0` và transcript final.
4. Chạy `kind=final`; chờ `analysis_runs.status=succeeded`.
5. Mở `http://127.0.0.1:${DASHBOARD_PORT}`; refresh sẽ tự chọn meeting mới nhất,
   tải transcript và nhận cập nhật SSE.
6. Xác minh model/version, KPI, timeline, evidence và DB cùng thuộc một UUID.

Nếu Dashboard trả `API 502` trong khi `/ready` trả 200, restart Dashboard để Nginx
phân giải lại Docker DNS sau khi backend recreate:

```bash
docker compose --env-file settings.env restart dashboard
```

## 9. Cập nhật release thủ công

Trước update, lưu hash/tag source đã chạy UAT pass. Quy trình deploy version mới:

```bash
cd /path/to/Buildkhoaluan/source
# 1. Lấy source version đã review (git pull / copy artifact theo quy trình nội bộ).
# 2. Không ghi đè settings.env.
docker compose --env-file settings.env config --quiet
docker compose --env-file settings.env up -d --build backend dashboard worker
./scripts/verify.sh
./scripts/smoke-analysis-pipeline.sh
```

Sau update, luôn chạy UAT smoke trước Google Meet thật.

## 10. Rollback thủ công

Rollback chỉ áp dụng khi build mới không pass health/smoke/UAT và có version trước
đã được lưu. Không rollback bằng cách xóa volume.

1. Quay source về commit/tag UAT-pass trước đó theo quy trình repository của bạn.
2. Giữ nguyên `source/settings.env` và Docker volumes.
3. Rebuild/recreate application:

```bash
cd /path/to/Buildkhoaluan/source
docker compose --env-file settings.env up -d --build backend dashboard worker
./scripts/verify.sh
```

4. Kiểm `/ready`, Dashboard và smoke pipeline. Nếu migration/schema thay đổi đã
được đưa vào một release tương lai, phải có rollback migration riêng trước khi
rollback code.

## 11. Dừng và khởi động lại an toàn

Dừng application nhưng giữ dữ liệu:

```bash
cd /path/to/Buildkhoaluan/source
docker compose --env-file settings.env down
```

Khởi động lại:

```bash
./scripts/vexa-selfhost.sh start
docker compose --env-file settings.env up -d
./scripts/verify.sh
```

Không dùng `down -v`, `docker volume rm`, hoặc reset database trong UAT nếu chưa có
backup và phê duyệt rõ ràng.

## 12. Chuẩn bị cho CI/CD sau UAT

CI/CD chưa phải dependency của release hiện tại. Khi bắt đầu áp dụng, pipeline tối
thiểu nên chạy theo thứ tự:

```text
lint + pytest + JavaScript syntax check
→ Docker build backend/dashboard
→ Compose config validation
→ synthetic smoke pipeline trên runner cô lập
→ publish image có tag immutable
→ manual approval
→ deploy UAT
→ UAT acceptance Google Meet có consent
```

Không đưa `settings.env`, Vexa token, DB backup hoặc transcript thật vào CI variables,
log CI hay image Docker. CI chỉ nên dùng secret manager và synthetic fixtures.

## 13. Checklist bàn giao UAT

| Hạng mục | Pass/Fail | Ghi chú |
| --- | --- | --- |
| Source/release version được ghi nhận | ☐ / ☐ |  |
| `settings.env` quyền 600, không có placeholder | ☐ / ☐ |  |
| Vexa gateway + transcription health | ☐ / ☐ |  |
| Application `/ready` và Dashboard HTTP 200 | ☐ / ☐ |  |
| Worker không có lỗi DB password mới | ☐ / ☐ |  |
| Synthetic smoke pass | ☐ / ☐ |  |
| Google Meet E2E có consent pass | ☐ / ☐ |  |
| Final analysis `succeeded` | ☐ / ☐ |  |
| Dashboard/model/evidence khớp API/DB | ☐ / ☐ |  |
| Backup (nếu có dữ liệu UAT cần giữ) | ☐ / ☐ |  |
| Không có secret/PII trong evidence | ☐ / ☐ |  |
