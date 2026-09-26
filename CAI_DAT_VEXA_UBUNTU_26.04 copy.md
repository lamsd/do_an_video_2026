# Cài đặt Vexa trên Ubuntu 26.04 LTS

Tài liệu này cài **Vexa self-hosted full stack** bằng Docker Compose (`make all`) trên Ubuntu 26.04 (codename `resolute`). Mỗi bước có một checkpoint; chỉ sang bước sau khi bước trước thành công.

> Lưu ý tương thích: Vexa hiện công bố Ubuntu 24.04 là mục tiêu production. Ubuntu 26.04 chưa được nêu là nền tảng production chính thức, nhưng Vexa chạy trong container Docker nên đây là đường cài đặt phù hợp để đánh giá/PoC.
>
> Lưu ý Jitsi: Vexa 0.12 xác nhận luồng Jitsi (join + capture) đã được kiểm chứng offline, còn live validation đang chờ. Cài đặt thành công chưa đồng nghĩa bot chắc chắn sẽ vào được mọi phòng Jitsi công khai; phải kiểm thử phòng thật ở checkpoint cuối.

## Kết quả triển khai hiện tại

Đã xác nhận trên môi trường này:

- Docker Engine hoạt động sau khi tài khoản được thêm vào nhóm `docker`.
- Full Vexa Compose stack đã lên.
- Bot image `vexaai/vexa-bot:v012` đã được tải.
- STT local đã chạy riêng tại `http://192.168.1.239:8083`, trả `/health` = `200`, dùng `large-v3-turbo` trên CUDA (`int8`).
- Vexa Compose đã được cấu hình để gọi STT local; gateway và các service dài hạn đang healthy.

Chưa xác nhận: bot Google Meet được tạo với `transcribe_enabled: true`, transcript thực tế, speaker attribution, AI pipeline và Chrome Extension. Mục tiêu kế tiếp là chạy một Meet thử, admit bot và đọc `segments` từ API.

## 0. Phạm vi và yêu cầu

- Không cài Vexa trực tiếp lên host: tất cả dịch vụ Vexa chạy trong Docker.
- Cần quyền `sudo`, Internet để tải Docker image và ít nhất vài GB dung lượng trống.
- `make all` cần Docker Engine **>= 26**.
- Để có transcript, cần một trong hai: transcription token của Vexa, hoặc dịch vụ STT tương thích OpenAI tự host trên GPU.
- Không dùng `make dev` trong hướng dẫn này: nó dành cho contributor và cần nhiều CPU/RAM hơn.

## 1. Kiểm tra máy chủ

```bash
uname -a
cat /etc/os-release
nproc
free -h
df -h /
lspci | grep -Ei 'vga|3d|nvidia' || true
nvidia-smi || true
```

**Checkpoint 1 — pass khi:** có quyền sudo, có disk trống hợp lý (khuyến nghị tối thiểu 20 GB cho PoC), và biết máy có GPU NVIDIA hay không. GPU không bắt buộc khi dùng transcription token bên ngoài.

## 2. Cập nhật hệ điều hành và cài công cụ cơ bản

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl git make gnupg
git --version
make --version
curl --version
```

**Checkpoint 2 — pass khi:** ba lệnh phiên bản cuối đều trả về phiên bản, không có lỗi apt chưa giải quyết.

## 3. Cài Docker Engine và Docker Compose plugin

Cài từ Docker apt repository chính thức, thay vì dùng gói `docker.io` cũ của Ubuntu.

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

```bash
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Kiểm tra Docker bằng `sudo` trước:

```bash
sudo systemctl enable --now docker
sudo docker run --rm hello-world
docker --version
docker compose version
```

**Nếu `sudo apt update` báo Docker chưa có repository cho `resolute`:** dừng tại đây, không tự đổi sang codename Ubuntu khác. Gửi nguyên văn lỗi để xác định phương án Docker Engine tương thích.

**Checkpoint 3 — pass khi:** `hello-world` chạy xong và Docker Engine là v26 trở lên.

## 4. Cho phép tài khoản hiện tại dùng Docker không cần sudo

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker run --rm hello-world
docker info --format '{{.ServerVersion}}'
```

`newgrp docker` chỉ có hiệu lực trong terminal hiện tại. Nếu không dùng được, đăng xuất/đăng nhập lại rồi mở terminal mới.

**Checkpoint 4 — pass khi:** `docker run --rm hello-world` chạy thành công mà không dùng `sudo`.

## 5. Clone Vexa và kiểm tra đúng release/source

Chọn một thư mục làm nơi chứa mã nguồn. Ví dụ dùng `~/src`:

```bash
mkdir -p ~/src
cd ~/src
git clone https://github.com/Vexa-ai/vexa.git
cd vexa
git status --short --branch
git log -1 --oneline
git tag --sort=-version:refname | head -n 10
sed -n '1,260p' README.md
make help
```

Không sửa source hoặc tạo file `.env` thủ công ở bước này. Ghi lại commit hiện tại; đó là phiên bản sẽ được dùng khi chẩn đoán lỗi.

**Checkpoint 5 — pass khi:** repository sạch, thấy target `all` trong `make help`, và README xác nhận `make all` là full Compose stack.

## 6. Chuẩn bị cấu hình Compose và secrets

`make all` chạy Makefile trong `deploy/compose`; do đó file môi trường thực tế là:

```text
<thu-muc-vexa>/deploy/compose/.env
```

Tạo file từ template trước khi khởi động lần đầu:

```bash
cd ~/src/vexa/deploy/compose
test -f .env || cp .env.example .env
```

Trước khi stack có thể healthy, tạo ba secret độc lập:

```bash
openssl rand -hex 32
```

Tạo ba lần và điền các giá trị vào `deploy/compose/.env`:

```dotenv
ADMIN_TOKEN=<secret-1>
INTERNAL_API_SECRET=<secret-2>
VEXA_FLOWS_API_KEY=<secret-3>
```

Giữ `VEXA_FLOWS_ADMIN_KEY=` trống: Compose sẽ dùng `ADMIN_TOKEN` cho flows. Bảo vệ file local:

```bash
chmod 600 deploy/compose/.env
```

Không dùng các giá trị placeholder như `changeme`, `secret`, hoặc `vexa-internal-secret`; Vexa từ chối chúng. Không commit `.env` và không gửi các giá trị này vào chat.

### 6.1 Sửa bot image tag không được expand lồng nhau

Trong một số checkout v0.12, template đặt `BROWSER_IMAGE=vexaai/vexa-bot:${IMAGE_TAG}`. Compose không expand biến lồng nhau theo cách runtime cần. Đặt tag cụ thể:

```dotenv
IMAGE_TAG=v012
BROWSER_IMAGE=vexaai/vexa-bot:v012
```

## 7. Khởi chạy full Vexa stack

Từ thư mục repository đã clone:

```bash
cd ~/src/vexa
docker pull vexaai/vexa-bot:v012
make all
```

Lệnh này tải các image đã được Vexa release-validate, khởi tạo `deploy/compose/.env` nếu cần, và đưa full Docker Compose stack lên. Khi hoàn thành, Vexa in ra URL Terminal, API gateway, và API key cục bộ.

**Bảo mật:** API key là secret. Không chụp/dán dòng key vào ticket công khai hoặc Chrome Extension. Lưu nó trong password manager hoặc biến môi trường của backend khi sang phase tích hợp.

Kiểm tra sau khi `make all` kết thúc:

```bash
cd ~/src/vexa/deploy/compose
docker compose ps
curl -fsS http://localhost:18056/health
```

Nếu repository yêu cầu compose file cụ thể, xem output `make all` hoặc chạy:

```bash
docker compose -f deploy/compose/docker-compose.yml ps
```

**Checkpoint 7 — pass khi:** gateway health trả về thành công, các service dài hạn ở trạng thái healthy/running, và lệnh sau in `vexaai/vexa-bot:v012`:

```bash
docker image inspect vexaai/vexa-bot:v012 --format '{{.RepoTags}}'
```

Gateway mặc định ở `http://localhost:18056`; Terminal UI ở `http://localhost:13000`. Gateway local là HTTP, không phải HTTPS.

### 7.1 Lỗi MinIO Docker Hub hiện tại

Một số checkout v0.12 khai báo `minio/minio:latest` và `minio/mc:latest`. Nếu Docker trả `pull access denied`, đó là lỗi upstream image registry, không phải lỗi Docker daemon.

Không dùng `quay.io/minio/aistor/minio` cho PoC không license: nó khởi động ở offline mode và từ chối mọi thao tác S3. Với **PoC local, không public Internet và không có dữ liệu thật**, có thể dùng tạm MinIO Community legacy:

```yaml
# deploy/compose/docker-compose.yml
minio:
  image: quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z
```

Giữ client init là `quay.io/minio/aistor/mc:latest` nếu nó pull được. Legacy image không được khuyến nghị cho production; môi trường production cần một object store S3-compatible đang được hỗ trợ và được kiểm định bảo mật.

## 8. Smoke test không dùng phòng họp thật

```bash
cd ~/src/vexa
make probe
```

`make probe` kiểm tra journey qua gateway (spawn → schedule → boot → join → transcript/live view → stop). Với image bot thật, meeting URL giả phải kết thúc bằng lỗi join có tên; đây là kết quả trung thực, không phải “xanh” giả.

**Checkpoint 8 — pass khi:** output nêu rõ từng stage, không có service crash/healthcheck fail. Nếu lỗi, thu log theo service lỗi thay vì sửa nhiều thành phần cùng lúc:

```bash
docker compose -f deploy/compose/docker-compose.yml ps
docker compose -f deploy/compose/docker-compose.yml logs --tail=200 gateway meeting-api runtime
```

## 9. Checkpoint bot join — tách khỏi transcription

Chỉ chạy khi checkpoint 7–8 đã pass. Dùng một terminal giữ API key trong memory, không dán key vào command history hay chat:

```bash
read -rsp 'Vexa API key: ' API_KEY; echo
export API_BASE=http://localhost:18056
```

### 9.1 Google Meet

Mở Google Meet với tư cách host. Với URL `https://meet.google.com/abc-defg-hij`, native meeting ID là `abc-defg-hij`.

```bash
export MEETING_ID=abc-defg-hij

curl -sS -X POST "$API_BASE/bots" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  --data "{\"platform\":\"google_meet\",\"native_meeting_id\":\"$MEETING_ID\",\"bot_name\":\"Vexa Test Bot\",\"transcribe_enabled\":false,\"recording_enabled\":false}"
```

Admit bot trong Google Meet nếu host nhận được yêu cầu. `transcribe_enabled: false` giúp chứng minh riêng luồng bot join trước khi cấu hình STT.

### 9.2 Jitsi Meet online

Mở phòng thử nghiệm, ví dụ `https://meet.jit.si/vexa-poc-lamsd-20260919`, giữ host trong phòng, rồi chạy:

```bash
export ROOM_ID=vexa-poc-lamsd-20260919

curl -sS -X POST "$API_BASE/bots" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  --data "{\"platform\":\"jitsi\",\"native_meeting_id\":\"$ROOM_ID\",\"meeting_url\":\"https://meet.jit.si/$ROOM_ID\",\"bot_name\":\"Vexa Test Bot\",\"transcribe_enabled\":false,\"recording_enabled\":false}"
```

Jitsi trong source hiện tại yêu cầu `meeting_url`; chỉ `native_meeting_id` sẽ trả 422 với lỗi unsupported platform.

Kiểm tra bot đang chạy:

```bash
curl -sS -H "X-API-Key: $API_KEY" "$API_BASE/bots/status"
```

**Checkpoint 9 — tiêu chí thành công:**

1. Bot được tạo và runtime sinh workload bot.
2. Bot vào phòng Jitsi, vẫn kết nối, và có audio.
3. Bot xuất hiện trong phòng; host admit bot nếu platform có lobby.

Nếu bot không xuất hiện, thu evidence theo đúng layer:

```bash
cd ~/src/vexa/deploy/compose
docker compose ps
docker compose logs --tail=200 runtime meeting-api
docker ps -a --filter 'name=mtg-' --format 'table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}'
```

## 10. Checkpoint transcript và speaker attribution

### 10.1 Cấu hình STT

Thêm service URL và token do nhà cung cấp transcription cấp, hoặc URL/token của STT OpenAI-compatible tự host, vào `deploy/compose/.env`:

```dotenv
TRANSCRIPTION_SERVICE_URL=<https-url-cua-STT>
TRANSCRIPTION_SERVICE_TOKEN=<secret-token>
```

Sau đó áp dụng cấu hình mới:

```bash
cd ~/src/vexa
make all
```

Không tự đoán endpoint STT từ một token. Vexa yêu cầu cả URL và token; thiếu cấu hình, bot với transcription bật sẽ bị từ chối hoặc chỉ capture mà không có transcript.

### 10.1a STT local miễn phí trên NVIDIA GPU

Vexa tách STT thành Compose project riêng ở `deploy/transcription`. Máy host cần NVIDIA driver hoạt động và Docker cần NVIDIA Container Toolkit. Kiểm tra trước:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Nếu lệnh Docker báo `could not select device driver "nvidia" with capabilities: [[gpu]]`, cài và cấu hình toolkit rồi restart Docker:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends curl gnupg
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Tạo file môi trường cho STT. `API_TOKEN` là secret riêng; tạo giá trị mạnh và không gửi vào chat:

```bash
cd ~/src/vexa/deploy/transcription
test -f .env || cp .env.example .env
openssl rand -hex 32
```

Điền vào `deploy/transcription/.env`:

```dotenv
MODEL_SIZE=large-v3-turbo
COMPUTE_TYPE=int8
API_TOKEN=<secret-da-tao>
```

Khởi động và chờ model tải xong. Lần đầu có thể mất vài phút:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 transcription-worker-1
curl -i http://localhost:8083/health
```

**Checkpoint STT — pass khi:** worker `healthy`, log có `Model loaded successfully`, và `/health` trả `200` với `device: "cuda"`, `gpu_available: true`.

Lấy IPv4 LAN của host, rồi nối main stack tới endpoint đó. Không dùng `localhost` vì bot chạy trong container khác:

```bash
hostname -I
```

Ví dụ host là `192.168.1.239`, điền `deploy/compose/.env`:

```dotenv
TRANSCRIPTION_SERVICE_URL=http://192.168.1.239:8083
TRANSCRIPTION_SERVICE_TOKEN=<cung-gia-tri-voi-API_TOKEN-o-tren>
TRANSCRIPTION_MODEL=
TRANSCRIBE_ENABLED=true
```

Sau đó áp dụng lại stack chính:

```bash
cd ~/src/vexa
make all
```

### 10.2 Tạo bot Google Meet với transcription bật

Mở Google Meet với tư cách host và giữ phòng mở. Mã phòng là phần cuối URL; ví dụ URL `https://meet.google.com/abc-defg-hij` có mã là `abc-defg-hij`. Nhập API key ẩn, không dán key từ trang web/Markdown vào shell:

```bash
read -rsp 'Vexa API key: ' API_KEY; echo
export API_BASE=http://localhost:18056
export MEETING_ID=abc-defg-hij
```

Gửi bot vào phòng:

```bash
curl -sS -X POST "$API_BASE/bots" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  --data "{\"platform\":\"google_meet\",\"native_meeting_id\":\"$MEETING_ID\",\"bot_name\":\"Vexa Transcript\",\"transcribe_enabled\":true,\"recording_enabled\":false}"
```

Admit bot trong giao diện Meet nếu Google yêu cầu. Nói vài câu, đợi 30–60 giây cho STT xử lý, rồi đọc transcript:

```bash
curl -sS -H "X-API-Key: $API_KEY" \
  "$API_BASE/transcripts/google_meet/$MEETING_ID"
```

Để lưu response vào JSON:

```bash
curl -sS -H "X-API-Key: $API_KEY" \
  "$API_BASE/transcripts/google_meet/$MEETING_ID" \
  -o transcript.json
```

File response có mảng `segments`; mỗi segment có `text`, `start`, `end`, và `speaker` khi Vexa xác định được. Nếu lệnh `curl` trả lỗi, dùng `curl -i` (không dùng `-f`) để xem HTTP status, sau đó xem log:

```bash
cd ~/src/vexa/deploy/compose
docker compose logs --tail=150 meeting-api runtime
```

Lưu ý khi copy lệnh từ chat: gõ URL thô `http://localhost:18056`, không dùng dạng Markdown `[http://...](http://...)`; dấu `\` ở cuối dòng phải là ký tự cuối cùng, không có khoảng trắng sau nó.

Đổi `google_meet/$MEETING_ID` thành `jitsi/$ROOM_ID` khi test Jitsi.

**Checkpoint 10 — pass khi:** response có transcript segments với `text`, `start`, `end`, và speaker khi Vexa xác định được. Speaker có thể rỗng trong crosstalk; backend phải giữ trạng thái unknown thay vì gán danh tính đoán.

## Vận hành tối thiểu

```bash
# Xem trạng thái
cd ~/src/vexa/deploy/compose
docker compose ps

# Dừng stack, GIỮ dữ liệu volumes
docker compose down
```

Không dùng `make down` ở checkout này: target hiện tại gọi `docker compose down -v` và sẽ xóa volumes. Chỉ dùng `docker compose down -v` hoặc xóa volume khi bạn chủ động muốn xóa PostgreSQL/MinIO và toàn bộ dữ liệu cục bộ.

## Tài liệu nguồn

- [Vexa README](https://github.com/Vexa-ai/vexa/blob/main/README.md) — Quickstart, API, trạng thái Jitsi và transcription.
- [Vexa Compose deployment](https://github.com/Vexa-ai/vexa/blob/main/deploy/compose/README.md) — topology/healthcheck/full-journey probe.
- [Docker Engine trên Ubuntu](https://docs.docker.com/engine/install/ubuntu/) — Docker apt repository chính thức.
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) — cài GPU runtime cho Docker.
