# Cấu hình self-host duy nhất

`settings.env` là file cấu hình runtime duy nhất cho hai Compose project. File dùng `VEXA_COMPOSE_PROJECT_NAME`, không dùng Docker variable `COMPOSE_PROJECT_NAME`, để không đổi tên Compose project của application:

```text
settings.env
 ├─ Meeting Intelligence: backend, worker, dashboard, PostgreSQL, Valkey
 └─ Vexa meetings-only: Gateway, admin-api, meeting-api, runtime, PostgreSQL, MinIO
```

File này chứa secret nên đã bị Git ignore. Chỉ `settings.env.example` được commit.

## Tạo hoặc hợp nhất cấu hình

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
cp settings.env.example settings.env       # chỉ khi chưa có settings.env
chmod 600 settings.env
```

Nếu đã có `settings.env`, không ghi đè bằng `cp`. Nếu đã có `vexa/deploy/meetings-only/project.env`, chuyển toàn bộ khóa Vexa hiện có mà không in secret bằng lệnh:

```bash
./scripts/vexa-selfhost.sh import-legacy-config
```

Lệnh chỉ ghi/đồng bộ nhóm khóa Vexa vào `settings.env`; `project.env` không bị sửa hoặc xóa. Sau khi kiểm tra Vexa chạy ổn định bằng cấu hình mới, có thể lưu `project.env` như bản backup local hoặc xóa thủ công ở một bước riêng.

Các secret cần có giá trị riêng, không dùng `CHANGE_ME`:

| Nhóm | Khóa |
| --- | --- |
| Application database | `POSTGRES_PASSWORD` |
| Application ↔ Vexa webhook | `VEXA_WEBHOOK_SECRET` |
| Vexa database | `DB_PASSWORD` |
| Vexa MinIO | `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` |
| Vexa control plane | `ADMIN_TOKEN`, `INTERNAL_API_SECRET` |
| Transcription (nếu STT yêu cầu token) | `TRANSCRIPTION_SERVICE_TOKEN` |
| API key sau khi Vexa đã chạy | `VEXA_API_KEY` |

Tạo secret cục bộ nếu cần:

```bash
./scripts/generate-selfhost-secrets.sh
```

Không dùng một secret cho `POSTGRES_PASSWORD` và `DB_PASSWORD`.

## Khắc phục PostgreSQL Vexa báo sai mật khẩu

`DB_PASSWORD` chỉ được PostgreSQL đọc ở lần tạo volume đầu tiên. Nếu Vexa báo `password authentication failed for user "postgres"`, có hai hướng:

1. Có dữ liệu cần giữ: khôi phục đúng `DB_PASSWORD` đã dùng lúc tạo volume.
2. Đây là cài đặt mới, không cần giữ dữ liệu Vexa: sau khi kiểm tra cẩn thận, xóa chỉ volume Vexa rồi tạo lại bằng cấu hình hiện tại:

   ```bash
   cd vexa/deploy/meetings-only
   docker compose --env-file ../../../settings.env -f compose.yaml down -v
   ```

   Lệnh này xóa PostgreSQL, Redis và MinIO của Vexa; không xóa database của Meeting Intelligence. Không chạy nếu cần giữ transcript hoặc token Vexa hiện có.

## Khởi động theo thứ tự

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
chmod 755 scripts/vexa-selfhost.sh

./scripts/vexa-selfhost.sh check
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
./scripts/vexa-selfhost.sh mint-token
```

`mint-token` in token `vxa_...` một lần. Dán token đó vào `VEXA_API_KEY` trong `settings.env`, rồi khởi động ứng dụng:

```bash
docker compose --env-file settings.env up -d --build
./scripts/verify.sh
```

## Cấu hình transcription

Vexa có thể khởi động khi `TRANSCRIPTION_SERVICE_URL` trống, nhưng gửi bot với transcription bật sẽ trả `503`. URL phải truy cập được từ container `meeting-api`.

Với service transcription chạy cùng Docker host trên cổng `8083`, dùng IP LAN của host, ví dụ:

```dotenv
TRANSCRIPTION_SERVICE_URL=http://192.168.1.10:8083
TRANSCRIPTION_SERVICE_TOKEN=copy_the_API_TOKEN_value_here
```

Không dùng `http://127.0.0.1:8083`: trong container, địa chỉ đó là chính container Vexa chứ không phải máy host.

Nếu transcription chạy cùng Docker host, có thể đồng bộ URL/token từ `vexa/deploy/transcription/.env` vào `settings.env` mà không hiển thị token:

```bash
HOST_LAN_IP=192.168.1.239 ./scripts/vexa-selfhost.sh sync-transcription-config
```

## Kiểm tra cuối

```bash
./scripts/vexa-selfhost.sh status
./scripts/vexa-selfhost.sh verify
docker compose --env-file settings.env ps
curl --fail http://127.0.0.1:${API_PORT}/ready
```

Sau đó tạo một meeting, admit bot, đồng bộ transcript, chạy final analysis và kiểm tra evidence trên dashboard.
