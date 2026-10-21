# Meeting Intelligence: build, deploy và tích hợp Vexa

Đây là entry point duy nhất của hệ thống Meeting Intelligence. Nó hiện thực kiến trúc trong `Reports/thesis_latex_overleaf/main.pdf`:

```text
Google Meet -> Vexa -> FastAPI -> PostgreSQL/outbox -> Valkey Stream
                                              -> sentiment worker -> SSE -> Dashboard
```

Vexa là nhà cung cấp bot/transcript. Project sở hữu bản sao transcript, revision, phân tích sentiment, Dashboard và database riêng. PostgreSQL là source of truth; Valkey chỉ phục vụ queue/fan-out. Dashboard không gọi Vexa và không chứa API key.

## Cấu trúc

```text
source/
├── compose.yaml                 # một entry point build/chạy application
├── settings.env.example         # mẫu cấu hình duy nhất
├── settings.env                 # secret local, không commit
├── src/
│   ├── backend/                 # FastAPI, worker, tests và Dockerfile chung
│   └── dashboard/               # Dashboard static + Nginx image
├── scripts/
│   ├── bootstrap.sh
│   └── verify.sh
└── vexa/                        # Vexa meetings/transcript-only
```

`meeting-intelligence-backend/` được giữ nguyên trong giai đoạn chuyển đổi để không phá hủy source/cấu hình cũ. Chỉ `src/` và `compose.yaml` là đường build mới. Sau khi smoke test đạt và có backup, thư mục cũ có thể được archive hoặc xóa trong một thay đổi riêng.

Xem [SELFHOST_CONFIGURATION.md](SELFHOST_CONFIGURATION.md) để dùng một `settings.env` cho cả ứng dụng và Vexa, cũng như quy trình khắc phục lỗi password và khởi động lại an toàn.

## Điều kiện cần

Máy chạy cần Docker Engine đang hoạt động và Docker Compose v2. Python, uv, Nginx, PostgreSQL và Valkey được đóng trong container, không cần cài trên host. Vexa self-host cần Docker Engine 26+ và transcription credential/service. Không có cách an toàn để loại bỏ các điều kiện runtime cấp máy này.

## Cấu hình một file

Tạo đúng một file cấu hình runtime:

```bash
cd source
./scripts/bootstrap.sh
```

Sửa `settings.env` cục bộ. Các biến cần chú ý:

| Biến | Ý nghĩa |
| --- | --- |
| `POSTGRES_PASSWORD` | Password URL-safe cho PostgreSQL ứng dụng. |
| `VEXA_MODE` | Luôn là `self_host` cho project này. |
| `VEXA_API_BASE` | `http://gateway:8000` (Docker DNS trong Vexa network). |
| `VEXA_NETWORK` | `vexa-meetings_vexa`, external network do Vexa meetings-only tạo. |
| `VEXA_API_KEY` | API key scope bot/transcript, chỉ backend đọc. |
| `VEXA_WEBHOOK_SECRET` | Secret HMAC chia sẻ giữa Vexa và backend. |
| `VEXA_WEBHOOK_URL` | HTTPS URL public của `/v1/webhooks/vexa`; dùng khi cấu hình Vexa webhook. |

Không commit `settings.env`, không đặt key trong Dashboard và không log file này. Production phải thay mọi placeholder và lưu secret bằng secret manager hoặc file quyền `600`.

### Tạo secrets và Vexa API key

Sinh secret ngẫu nhiên cục bộ (script chỉ in ra terminal):

```bash
cd source
chmod 755 scripts/generate-selfhost-secrets.sh
./scripts/generate-selfhost-secrets.sh
```

Điền `POSTGRES_PASSWORD`, `VEXA_WEBHOOK_SECRET`, `DB_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `ADMIN_TOKEN`, `INTERNAL_API_SECRET` vào `settings.env`. Không dùng cùng một giá trị cho các biến database/secret độc lập.

Sau khi Vexa meetings-only đã chạy, mint API key có scope tối thiểu `bot,tx`:

```bash
cd source
chmod 755 scripts/vexa-selfhost.sh
./scripts/vexa-selfhost.sh mint-token
```

Lệnh in một token `vxa_...` duy nhất. Sao chép token đó vào `VEXA_API_KEY` trong `source/settings.env`; không đưa token vào README, log hoặc Git. Có thể dùng `EMAIL=you@example.com ./scripts/vexa-selfhost.sh mint-token` để cấp token cho identity khác.

## Bước 1 — build và test Vexa meetings-only

```bash
cd source
chmod 755 scripts/vexa-selfhost.sh
./scripts/vexa-selfhost.sh check
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
```

Topology chỉ gồm PostgreSQL, Valkey, MinIO, admin-api, runtime, meeting-api và Gateway. `verify.sh` kiểm Gateway healthy, route agent là `404` và MCP service không tồn tại. Agent, Terminal, MCP, flows, mailbox, extensions, release/dev tooling và CI metadata đã được loại bỏ; `runtime` được giữ vì nó spawn meeting bot.

## Bước 2 — build và chạy application

```bash
cd source
docker compose --env-file settings.env config
docker compose --env-file settings.env up -d --build
./scripts/verify.sh
```

Sau khi thành công:

- Dashboard: `http://localhost:${DASHBOARD_PORT}` (mặc định `3000`)
- Backend local/debug: `http://localhost:${API_PORT}/health`, `http://localhost:${API_PORT}/ready` (mặc định `8088`)

Dashboard chỉ bind `127.0.0.1`; production cần reverse proxy TLS phía trước. Không public PostgreSQL, Valkey, Vexa admin API hoặc Docker socket.

Dừng hệ thống nhưng giữ dữ liệu:

```bash
docker compose --env-file settings.env down
```

Không dùng `down -v` trong vận hành thông thường vì nó xóa named volumes của PostgreSQL và Valkey.

## Self-host dependency graph

```text
gateway -> admin-api -> meeting-api -> runtime -> spawned meeting bot
             |             |             |
             +----- PostgreSQL, Valkey, MinIO
```

Deployment thực tế là `source/vexa/deploy/meetings-only/compose.yaml`. Nó kế thừa định nghĩa core đã kiểm chứng từ `deploy/compose`, nhưng chỉ materialize services ở sơ đồ trên.

`http://gateway:8000` chỉ đúng trong Docker network `vexa-meetings_vexa`. Application Compose join network external này qua `VEXA_NETWORK`, do đó không hard-code network cũ `vexa-v012_vexa`.

## Webhook và contract Vexa

Backend dùng các Vexa endpoint: `POST /bots`, `GET /transcripts/{platform}/{native_id}` và `DELETE /bots/{platform}/{native_id}`, tất cả với `X-API-Key`. Browser không gọi các endpoint này.

Receiver `/v1/webhooks/vexa` xác minh:

```text
X-Webhook-Signature = sha256(HMAC(secret, "<X-Webhook-Timestamp>." + raw_body))
```

Để webhook hoạt động phải cấu hình cho **cùng user/API key** trước khi spawn bot qua `PUT /user/webhook`, gồm webhook URL, secret và event list được Vexa hỗ trợ. Sau đó kiểm chứng bằng `GET /user/webhook/deliveries` và bảng `incoming_webhooks` của application. Polling transcript vẫn là fallback khi webhook lỗi hoặc đến trễ.

Webhook cần endpoint HTTPS mà Vexa truy cập được. Không giả định `http://backend:8088` có thể được Vexa gọi: Docker DNS không đi xuyên hai Compose project và Vexa có SSRF policy.

## Kiểm thử và nghiệm thu

Trước mỗi demo, tạo biên bản runtime read-only (không in secret) bằng:

```bash
cd source
./scripts/runtime-status.sh
```

Script này xác nhận trạng thái Compose mới, `/ready`, port đang dùng và các container legacy đang cùng tồn tại.

Nếu application PostgreSQL đã được khởi tạo với password cũ nhưng `settings.env` đã đổi, đồng bộ lại role ứng dụng mà không xóa dữ liệu:

```bash
cd source
./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker
./scripts/verify.sh
```

Script chỉ cập nhật password của role hiện hành; không thực hiện `down -v` hay xóa volume.

Kiểm tra nội bộ luồng API → queue → worker mà không gọi Vexa hoặc lưu transcript thật:

```bash
cd source
./scripts/smoke-analysis-pipeline.sh
```

Script tạo hai segment tiếng Việt tổng hợp, chờ final analysis hoàn tất và xóa meeting fixture cùng dữ liệu phụ thuộc trước khi thoát.

Thực hiện theo thứ tự:

1. `docker compose ... config`: kiểm cấu hình, biến required và không có network/port hard-code.
2. Unit tests: quality rules, unit builder, classifier/config validation.
3. Integration: PostgreSQL/Valkey, outbox, idempotency `(meeting_id, kind, source_revision, model_version)`, retry/reclaim worker và SSE.
4. Dashboard smoke: UUID hợp lệ, KPI/timeline/evidence, refresh qua SSE; UUID sai không gọi API.
5. Vexa contract: spawn/read transcript/stop, webhook valid/tampered/replay và delivery ledger.
6. E2E: bot -> transcript -> analysis -> SSE -> Dashboard; restart backend/worker không mất data.

Không dùng transcript cuộc họp thật trong Git, fixture hoặc CI logs. Real-meeting test cần consent người tham gia. Baseline hiện hành là `baseline-rules-v2`; không ghi là PhoBERT cho đến khi có artifact versioned và báo cáo đánh giá.

## Model sentiment cho pilot

`rules` chỉ là baseline kiểm chứng pipeline. Adapter `tfidf-logreg` nạp một artifact scikit-learn versioned từ `/models`, kiểm tra SHA-256 và dừng worker khi artifact/config không nhất quán - không tự fallback sang rules. Quy trình tạo artifact, manifest dữ liệu và cách cấu hình runtime ở [model-data/README.md](model-data/README.md). Corpus đào tạo phải được phép sử dụng, tách khỏi transcript vận hành và không phải dữ liệu phân loại trầm cảm trong `Reports/`.

Use case pilot duy nhất là retrospective sau cuộc họp: người vận hành xem timeline, transcript và evidence tại Dashboard, không dùng output để đánh giá con người. Xem [pilot/retrospective/README.md](pilot/retrospective/README.md) trước khi chạy meeting thật; consent và dữ liệu thật không được đưa vào repository.

## Production checklist

- Pin Vexa version/commit và image digest; không dùng `latest`/`:dev` trong production.
- TLS reverse proxy, authentication thực (thay `X-App-User-Id` development), allow-list origin/rate limit.
- Backup/restore PostgreSQL đã test, retention/delete workflow và giám sát queue lag/API errors/latency.
- Deploy theo: pull image digest -> `up -d` -> `/ready` -> Dashboard smoke -> quan sát -> rollback digest trước nếu thất bại.
- Vexa database/MinIO volumes và application volumes là hai domain dữ liệu khác nhau, backup riêng.

## Giới hạn MVP

Không claim Zoom/Teams/Jitsi, direct Vexa WebSocket ingestion, JWT/OAuth, GPU benchmark, Kubernetes/HA, PhoBERT, auto-alert hoặc mental-health/HR scoring là đã triển khai. Đây là các giai đoạn sau, cần contract, consent và benchmark riêng.
