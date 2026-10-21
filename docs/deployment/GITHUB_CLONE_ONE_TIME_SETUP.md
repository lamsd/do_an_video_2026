# Cài đặt một lần từ GitHub và chạy Meeting Intelligence

> Mục tiêu: clone repository, cấu hình máy DEV/UAT nội bộ, build Docker **một lần**
> và sau đó chỉ dùng lệnh start/stop thông thường. Không cần CI/CD.
>
> Repository: `https://github.com/lamsd/do_an_video_2026`

## 1. Phạm vi nền tảng họp

| Nền tảng | Trạng thái hiện tại |
| --- | --- |
| Google Meet | Đã được backend hỗ trợ end-to-end; dùng trong hướng dẫn này |
| Zoom / Microsoft Teams / Jitsi | Chưa được API application hiện tại hỗ trợ; không gửi URL các nền tảng này vào `POST /v1/meetings` |

Vexa có thể có adapter riêng cho các nền tảng khác, nhưng muốn dùng chúng cần bổ sung
parser URL, provider contract và test E2E ở backend trước. Không coi đây là cấu hình
chỉ bằng biến môi trường.

## 2. Điều kiện máy (cài một lần)

Cần:

- Git.
- Docker Engine đang chạy.
- Docker Compose v2.
- `curl`.
- Quyền chạy Docker cho user hiện tại.
- Network cho Vexa bot vào Google Meet và máy Vexa truy cập được transcription service.

Kiểm tra:

```bash
git --version
docker info
docker compose version
curl --version
```

Nếu chạy transcription GPU, cài NVIDIA Container Toolkit. Không có GPU vẫn chạy được
qua CPU, nhưng inference chậm hơn.

## 3. Clone repository

```bash
git clone https://github.com/lamsd/do_an_video_2026.git
cd do_an_video_2026
test -f source/compose.yaml
test -d source/vexa
```

Không clone/copy `settings.env` từ Git: file này có secret theo máy và đã bị ignore.

## 4. Tạo runtime configuration một lần

```bash
cd source
./scripts/bootstrap.sh
chmod 600 settings.env
```

Mở `source/settings.env`, thay mọi `CHANGE_ME` bằng secret riêng. Tạo secret local
nếu cần:

```bash
./scripts/generate-selfhost-secrets.sh
```

Điền tối thiểu các giá trị sau vào `settings.env`:

```dotenv
POSTGRES_PASSWORD=<secret-url-safe>
DB_PASSWORD=<secret-khac-POSTGRES_PASSWORD>
MINIO_ACCESS_KEY=<secret>
MINIO_SECRET_KEY=<secret>
ADMIN_TOKEN=<secret>
INTERNAL_API_SECRET=<secret>
VEXA_WEBHOOK_SECRET=<secret>

VEXA_MODE=self_host
VEXA_NETWORK=vexa-meetings_vexa
RUNTIME_API_PORT=18190
```

Không để ký tự chữ trong host port, ví dụ `RUNTIME_API_PORT=18190z`; Compose sẽ lỗi
`invalid hostPort`.

## 5. Build transcription một lần

Transcription là STT. Không có STT thì bot vẫn vào Meet nhưng transcript sẽ luôn
`total: 0`.

### CPU

```bash
cd source/vexa/deploy/transcription
docker compose -f docker-compose.cpu.yml up -d --build
curl --fail --show-error http://127.0.0.1:8083/health
```

### GPU

```bash
cd source/vexa/deploy/transcription
docker compose up -d --build
curl --fail --show-error http://127.0.0.1:8083/health
```

Chỉ chọn **một** trong hai cách. Sau build đầu, lần chạy thường chỉ cần
`docker compose up -d`, không cần `--build`.

## 6. Kết nối Vexa tới transcription một lần

Trở về `source`. Dùng IP LAN của máy chạy STT; không dùng `127.0.0.1` vì bot chạy
trong Docker container.

```bash
cd source
HOST_LAN_IP=<IP-LAN-cua-may-STT> ./scripts/vexa-selfhost.sh sync-transcription-config

STT_URL=$(awk -F= '$1 == "TRANSCRIPTION_SERVICE_URL" { print $2; exit }' settings.env)
curl --fail --show-error --max-time 5 "$STT_URL/health"
```

Nếu STT chạy trên máy khác, đặt thủ công `TRANSCRIPTION_SERVICE_URL` và
`TRANSCRIPTION_SERVICE_TOKEN` trong `settings.env`; URL phải reachable từ Vexa.

## 7. Build Vexa và lấy API key một lần

```bash
cd source
./scripts/vexa-selfhost.sh check
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
./scripts/vexa-selfhost.sh mint-token
```

`mint-token` in token `vxa_...` một lần. Dán token đó vào:

```dotenv
VEXA_API_KEY=<token-vxa>
```

Sau khi lưu `settings.env`, nạp lại Vexa:

```bash
./scripts/vexa-selfhost.sh start
```

## 8. Build application một lần

```bash
cd source
docker compose --env-file settings.env config --quiet
docker compose --env-file settings.env up -d --build

./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker
./scripts/verify.sh
```

Kiểm worker không còn lỗi password mới:

```bash
docker compose --env-file settings.env logs --since=2m --tail=80 worker
```

Khi tất cả pass, build ban đầu hoàn tất.

## 9. Lệnh chạy thường ngày (không build lại)

Sau lần build đầu, dùng:

```bash
cd /path/to/do_an_video_2026/source
./scripts/vexa-selfhost.sh start
docker compose --env-file settings.env up -d
./scripts/verify.sh
```

Lấy URL thật từ file config:

```bash
API_PORT=$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env)
API_PORT=${API_PORT:-8088}
DASHBOARD_PORT=$(awk -F= '$1 == "DASHBOARD_PORT" { print $2; exit }' settings.env)
DASHBOARD_PORT=${DASHBOARD_PORT:-3000}

echo "API:       http://127.0.0.1:${API_PORT}"
echo "Dashboard: http://127.0.0.1:${DASHBOARD_PORT}"
```

Không tự giả định port `8088`/`3000`, vì chúng có thể bị stack legacy chiếm.

## 10. Test sau cài đặt

Chạy test không dùng dữ liệu thật:

```bash
cd source
./scripts/smoke-analysis-pipeline.sh
```

Kết quả đúng:

```text
PASS: synthetic fixture completed API -> queue -> worker -> analytics API.
```

Sau đó test Google Meet theo [DEV_INSTALL_RUN_TEST_DASHBOARD_GUIDE.md](../operations/DEV_INSTALL_RUN_TEST_DASHBOARD_GUIDE.md):

1. Tạo Google Meet có consent.
2. Gọi `POST /v1/meetings` với Meet URL.
3. Admit bot, nói 15–20 giây và chờ STT xử lý.
4. Xác nhận sync có `total > 0`.
5. Chạy final analysis.
6. Refresh Dashboard; nó tự chọn meeting mới nhất và hiển thị transcript/kết quả.

## 11. Khi nào cần build lại?

Chỉ chạy `docker compose ... up -d --build` khi:

- mới clone lần đầu;
- source code, Dockerfile, `pyproject.toml`, dashboard assets hoặc dependency thay đổi;
- bạn đã `git pull` version mới cần áp dụng.

Nếu chỉ restart máy/container hoặc bắt đầu cuộc họp mới, dùng lệnh ở Mục 9, không
cần build lại.

## 12. Dừng an toàn

```bash
cd source
docker compose --env-file settings.env down
```

Lệnh trên giữ PostgreSQL/Valkey volumes. Không chạy `docker compose down -v` nếu
muốn giữ transcript, analysis, token hoặc dữ liệu local.
