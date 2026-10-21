# Build lại hệ thống sau khi xóa Docker

Tài liệu này hướng dẫn dựng lại toàn bộ môi trường Meeting Intelligence từ trạng thái Docker đã bị xóa: Docker Engine, transcription/STT, Vexa, backend, worker, database và Dashboard.

Kiến trúc cần dựng:

```text
Google Meet → Vexa + transcription → FastAPI → PostgreSQL / Valkey
                                      → sentiment worker → Dashboard
```

> Phạm vi build duy nhất là `source/compose.yaml` và Vexa meetings-only. Không dùng `source/meeting-intelligence-backend/` vì đó là stack legacy.

## 1. Cài lại Docker Engine và Docker Compose

Chỉ thực hiện bước này khi lệnh `docker` không còn hoạt động. Nếu Docker Engine vẫn được cài nhưng bạn chỉ xóa container, image và volume thì sang thẳng Mục 2.

```bash
sudo apt update
sudo apt install -y ca-certificates curl git make gnupg

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

```bash
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"${UBUNTU_CODENAME:-$VERSION_CODENAME}\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

Cho phép tài khoản hiện tại chạy Docker mà không cần `sudo`:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

Kiểm tra checkpoint:

```bash
docker run --rm hello-world
docker info
docker compose version
```

**Pass:** `hello-world` chạy thành công và Docker Engine là phiên bản 26 trở lên.

## 2. Chuẩn bị cấu hình runtime

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
chmod +x scripts/*.sh
./scripts/bootstrap.sh
chmod 600 settings.env
```

Mở file cấu hình local:

```bash
nano settings.env
```

Thay toàn bộ `CHANGE_ME` ở các giá trị bắt buộc. Không được đưa file này lên Git hoặc gửi lên chat.

```dotenv
POSTGRES_PASSWORD=<password-url-safe>
DB_PASSWORD=<password-khac-postgres>
MINIO_ACCESS_KEY=<secret>
MINIO_SECRET_KEY=<secret>
ADMIN_TOKEN=<secret>
INTERNAL_API_SECRET=<secret>
VEXA_WEBHOOK_SECRET=<secret>
```

- `POSTGRES_PASSWORD` và `DB_PASSWORD` phải khác nhau.
- Password database chỉ nên dùng chữ, số, `-` và `_`.
- Giữ `VEXA_NETWORK=vexa-meetings_vexa`.
- Không đặt `COMPOSE_PROJECT_NAME` trong `settings.env`.

Nếu cần tạo secret, dùng:

```bash
./scripts/generate-selfhost-secrets.sh
```

## 3. Build transcription/STT

Chọn **một** trong hai phương án sau.

### CPU

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source/vexa/deploy/transcription
docker compose -f docker-compose.cpu.yml up -d --build
curl --fail --show-error http://127.0.0.1:8083/health
```

### NVIDIA GPU

Yêu cầu NVIDIA Container Toolkit đã được cài đặt trước.

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source/vexa/deploy/transcription
docker compose up -d --build
curl --fail --show-error http://127.0.0.1:8083/health
```

**Pass:** endpoint `/health` trả HTTP 200.

## 4. Kết nối Vexa với transcription

Vexa chạy trong container, vì vậy không dùng `127.0.0.1` làm URL transcription trong `settings.env`.

Lấy IP LAN của máy:

```bash
hostname -I
```

Ví dụ IP máy là `192.168.1.50`:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
HOST_LAN_IP=192.168.1.50 ./scripts/vexa-selfhost.sh sync-transcription-config
./scripts/vexa-selfhost.sh check
```

**Pass:** script báo `Configuration is valid.`. Nếu STT chạy ở máy khác, đặt thủ công `TRANSCRIPTION_SERVICE_URL` và `TRANSCRIPTION_SERVICE_TOKEN` sao cho Vexa truy cập được.

## 5. Build và chạy Vexa meetings-only

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source

./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
./scripts/vexa-selfhost.sh status
```

**Pass:** có dòng sau:

```text
Verified: Vexa meetings-only gateway is healthy.
```

Sau đó tạo API key cho backend:

```bash
./scripts/vexa-selfhost.sh mint-token
```

Lệnh chỉ in token `vxa_...` một lần. Sao chép nó vào `settings.env`:

```dotenv
VEXA_API_KEY=vxa_...
```

Sau khi lưu file, nạp lại Vexa:

```bash
./scripts/vexa-selfhost.sh start
```

## 6. Build application

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source

docker compose --env-file settings.env config --quiet
docker compose --env-file settings.env up -d --build
```

Lần dựng đầu có thể mất vài phút vì Docker cần tải PostgreSQL, Valkey, Nginx và build backend/Dashboard.

## 7. Đồng bộ password và kiểm tra runtime

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source

./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker

./scripts/runtime-status.sh
./scripts/verify.sh
```

Kiểm tra log worker:

```bash
docker compose --env-file settings.env logs --since=2m --tail=80 worker
```

**Pass:** backend `/ready` và Dashboard trả HTTP 200; worker không có `InvalidPasswordError`.

## 8. Chạy smoke test không dùng cuộc họp thật

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/smoke-analysis-pipeline.sh
```

**Pass:**

```text
PASS: synthetic fixture completed API -> queue -> worker -> analytics API.
```

## 9. Lấy URL Dashboard và API

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source

API_PORT=$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env)
API_PORT=${API_PORT:-8088}

DASHBOARD_PORT=$(awk -F= '$1 == "DASHBOARD_PORT" { print $2; exit }' settings.env)
DASHBOARD_PORT=${DASHBOARD_PORT:-3000}

echo "API: http://127.0.0.1:${API_PORT}"
echo "Dashboard: http://127.0.0.1:${DASHBOARD_PORT}"
```

Mặc định Dashboard ở `http://127.0.0.1:3000` và API ở `http://127.0.0.1:8088`.

## 10. Kiểm thử Google Meet thật

Chỉ chạy bước này khi Mục 1–8 đã pass và mọi người tham gia đã đồng ý (consent). Làm theo tài liệu `docs/operations/GOOGLE_MEET_E2E_VERIFICATION_CHECKLIST.md` tại thư mục gốc dự án.

## Lệnh dùng hằng ngày

Sau lần build đầu, không cần `--build` trừ khi source, Dockerfile hoặc dependency thay đổi:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/vexa-selfhost.sh start
docker compose --env-file settings.env up -d
./scripts/verify.sh
```

Dừng stack nhưng vẫn giữ dữ liệu:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
docker compose --env-file settings.env down
```

> Không chạy `docker compose down -v`, `docker volume rm` hoặc reset database nếu muốn giữ transcript, analysis và dữ liệu local.
