# Triển khai portable trên nhiều máy: build một lần, chạy nhiều nơi

> Mục tiêu: di chuyển Meeting Intelligence sang nhiều máy DEV/UAT nhanh, không
> dùng CI/CD, hạn chế build lặp lại và không ảnh hưởng dữ liệu/cấu hình giữa máy.

## 1. Nguyên tắc quan trọng

| Thành phần | Có chuyển giữa máy không? | Quy tắc |
| --- | --- | --- |
| Source code | Có | Cùng Git tag/commit đã được kiểm thử |
| Backend/Dashboard Docker image | Có | Build một lần trên máy release rồi `docker save`/`docker load` |
| `settings.env` | Không | Mỗi máy tự tạo secret, port và STT endpoint riêng |
| PostgreSQL/Valkey volumes | Không | Mỗi máy có dữ liệu độc lập |
| Vexa token | Không nên | Mint API key riêng cho từng Vexa environment |
| Transcript thật | Không | Không copy vào image, Git hoặc gói release |

Chỉ clone repository **không** làm image có sẵn. Nếu muốn không build lại ở mọi
máy, cần dùng một trong hai cách:

1. **Manual image bundle** (dùng trong tài liệu này): `docker save` ở máy release,
   copy file `.tar`, `docker load` ở máy đích.
2. **Container registry** (giai đoạn sau): push image tag immutable, target pull image.

## 2. Chuẩn bị một bản release đã pass

Trên máy release/dev, chỉ thực hiện sau khi synthetic test và Google Meet E2E pass.
Ghi lại Git tag hoặc commit để tất cả máy dùng cùng source version.

```bash
cd /path/to/do_an_video_2026
git rev-parse --short HEAD
```

Build image application một lần:

```bash
cd source
docker compose --env-file settings.env build backend dashboard
docker image ls meeting-intelligence-backend meeting-intelligence-dashboard
```

Đóng gói hai image tự build. Dùng timestamp để không overwrite release khác:

```bash
RELEASE_ID=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /tmp/meeting-intelligence-release

docker save \
  -o "/tmp/meeting-intelligence-release/meeting-intelligence-${RELEASE_ID}.tar" \
  meeting-intelligence-backend:local \
  meeting-intelligence-dashboard:latest

sha256sum "/tmp/meeting-intelligence-release/meeting-intelligence-${RELEASE_ID}.tar" \
  > "/tmp/meeting-intelligence-release/meeting-intelligence-${RELEASE_ID}.tar.sha256"
```

Chỉ gói image; không gói `settings.env`, volumes, database dump hoặc transcript.

## 3. Chuyển release sang máy đích

Trên mỗi máy đích, cài Git + Docker Engine + Docker Compose v2 trước.

Clone đúng source release:

```bash
git clone https://github.com/lamsd/do_an_video_2026.git
cd do_an_video_2026
git checkout <git-tag-hoac-commit-da-pass>
```

Chuyển file `.tar` và `.sha256` bằng USB/SCP/private storage. Trên máy đích, kiểm
checksum trước khi load:

```bash
sha256sum -c meeting-intelligence-<release-id>.tar.sha256
docker load -i meeting-intelligence-<release-id>.tar
docker image ls meeting-intelligence-backend meeting-intelligence-dashboard
```

**Pass:** checksum `OK`; hai image hiện diện local. Từ đây application không cần
`--build` trên máy đích.

## 4. Cấu hình độc lập cho từng máy

Trong mỗi repository clone:

```bash
cd source
./scripts/bootstrap.sh
chmod 600 settings.env
```

Mỗi máy phải dùng secret riêng cho:

```text
POSTGRES_PASSWORD, DB_PASSWORD, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
ADMIN_TOKEN, INTERNAL_API_SECRET, VEXA_WEBHOOK_SECRET
```

Không sao chép nguyên `settings.env` từ máy release. Những giá trị phải điều chỉnh
theo máy:

```dotenv
API_PORT=<port-chua-dung>
DASHBOARD_PORT=<port-chua-dung>
TRANSCRIPTION_SERVICE_URL=http://<IP-LAN-STT>:8083
VEXA_NETWORK=vexa-meetings_vexa
RUNTIME_API_PORT=18190
```

Nếu các máy chạy riêng biệt, có thể dùng cùng port mặc định vì port/volume của mỗi
host vốn tách biệt. Nếu chạy nhiều instance trên **cùng một host**, phải đổi toàn
bộ host port và compose project/volume strategy trước; không dùng chung database
volume giữa instance.

## 5. Dựng dependency trên máy đích

### 5.1 Transcription

STT có thể cần image riêng. Trên mỗi máy STT, hoặc build CPU/GPU một lần hoặc export
image này theo phương pháp ở Mục 2.

```bash
cd source/vexa/deploy/transcription
docker compose -f docker-compose.cpu.yml up -d
# GPU: docker compose up -d
curl --fail --show-error http://127.0.0.1:8083/health
```

Nếu image transcription chưa tồn tại local, Compose sẽ cần build lần đầu. Đây là
dependency tách riêng, không phải backend/dashboard image bundle.

### 5.2 Vexa

```bash
cd source
./scripts/vexa-selfhost.sh check
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
```

Mint API key riêng cho máy này, đặt vào `VEXA_API_KEY` trong `settings.env`, rồi
nạp lại Vexa:

```bash
./scripts/vexa-selfhost.sh mint-token
./scripts/vexa-selfhost.sh start
```

Đồng bộ endpoint STT nếu STT dùng cùng host LAN:

```bash
HOST_LAN_IP=<IP-LAN-STT> ./scripts/vexa-selfhost.sh sync-transcription-config
./scripts/vexa-selfhost.sh start
```

## 6. Chạy application ở máy đích, không build lại

```bash
cd source
docker compose --env-file settings.env config --quiet
docker compose --env-file settings.env up -d

./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker
./scripts/verify.sh
```

Không thêm `--build` ở bước này. Compose dùng image đã `docker load`.

## 7. Acceptance tối thiểu trên từng máy

Không xem máy đích là deploy thành công chỉ vì container đang Up. Chạy lần lượt:

```bash
cd source
./scripts/runtime-status.sh
./scripts/smoke-analysis-pipeline.sh
```

Sau đó chạy Google Meet E2E theo [DEV_INSTALL_RUN_TEST_DASHBOARD_GUIDE.md](../operations/DEV_INSTALL_RUN_TEST_DASHBOARD_GUIDE.md):

1. Bot được admit.
2. Sync transcript có `total > 0`.
3. Final analysis có `status=succeeded`.
4. Dashboard tự tải meeting mới nhất và transcript/evidence đúng.

## 8. Cập nhật version cho nhiều máy

Mỗi update chỉ cần thực hiện lại trên máy release:

```text
source mới → test → build image → docker save → checksum → phân phối tar
```

Trên mỗi máy đích:

```text
git checkout đúng tag/commit → verify checksum → docker load → docker compose up -d
→ smoke test → UAT E2E
```

Rollback = checkout source tag cũ + `docker load` image bundle cũ + `docker compose up -d`.
Không rollback bằng cách xóa volumes.

## 9. Checklist portable deployment

| Hạng mục | Pass/Fail |
| --- | --- |
| Cùng Git tag/commit trên mọi máy | ☐ / ☐ |
| Image bundle checksum hợp lệ | ☐ / ☐ |
| Không chuyển `settings.env`/volumes/transcript | ☐ / ☐ |
| Secret và Vexa API key riêng theo máy | ☐ / ☐ |
| STT reachable từ Vexa | ☐ / ☐ |
| Application chạy không cần `--build` | ☐ / ☐ |
| Synthetic smoke pass | ☐ / ☐ |
| Google Meet E2E pass | ☐ / ☐ |
| Dashboard/API/DB đúng trên máy đích | ☐ / ☐ |
