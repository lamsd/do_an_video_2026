# Backend Meeting Intelligence: thiết kế và hướng dẫn triển khai

Tài liệu này gộp kiến trúc và kế hoạch triển khai backend nhận transcript từ Vexa để phục vụ hiển thị **realtime**, **near-realtime** và **phân tích sau khi meeting kết thúc**.

Phạm vi MVP là Google Meet + Vexa self-hosted + STT local GPU hiện có. Sau khi luồng này pass mới mở rộng Jitsi/Teams/Zoom.

## 1. Mục tiêu và nguyên tắc

Backend là lớp trung gian duy nhất giữa Vexa và Chrome Extension/Web UI.

```text
Google Meet → Vexa Bot → STT local → Vexa
                                      │
                                      ▼
                              Backend Meeting Intelligence
                               ├── PostgreSQL: dữ liệu chuẩn
                               ├── Redis: event queue/fan-out
                               ├── Live API: WS/SSE cho UI
                               └── AI workers: insight/final analysis
                                      │
                                      ▼
                             Chrome Extension / Web UI
```

Nguyên tắc bắt buộc:

- Extension không biết Vexa API key, Vexa STT token hay webhook secret.
- Backend không đọc Redis/PostgreSQL nội bộ của Vexa; chỉ dùng API/WebSocket/webhook chính thức.
- WebSocket giảm latency nhưng REST transcript là reconciliation/source-of-truth fallback.
- Webhook là at-least-once; phải dedupe theo `event_id`.
- Không chạy LLM trên từng draft transcript; chỉ phân tích theo cửa sổ segment finalized hoặc lúc end-call.

## 2. Ba luồng dữ liệu cần hỗ trợ

| Loại dữ liệu | Cơ chế chính | Fallback / bảo đảm dữ liệu |
|---|---|---|
| Realtime trạng thái bot | Vexa WS `/ws`, frame `meeting.status` | poll `/bots/status` hoặc `/meetings` |
| Realtime transcript | Vexa WS `/ws`, frame `transcript` / `transcription_segment` | poll `/transcripts/{platform}/{native_meeting_id}` mỗi 3–5 giây |
| End-call | Vexa system webhook `meeting.completed` / `bot.failed` | poll trạng thái rồi final REST reconciliation |

### Quy tắc latency

- Mục tiêu realtime P95: Vexa WS frame → backend client event dưới 2 giây.
- Mục tiêu near-realtime P95: transcript xuất hiện dưới 5 giây khi WS không dùng được.
- Sau backend reconnect: REST reconciliation sửa chênh lệch trong dưới 15 giây.

## 3. Kiến trúc runtime

```text
                         Vexa /ws
                            │
                            ▼
                     Vexa WS ingestor
                            │ normalize + dedupe
                            ▼
          ┌──────────── PostgreSQL ────────────┐
          │ meetings / segments / webhook log  │
          │ outbox events / analysis results   │
          └────────────────┬───────────────────┘
                           │ transactional outbox
                           ▼
                   Redis Streams + Pub/Sub
                    │                    │
                    ▼                    ▼
            app WS / SSE gateway     analysis workers
                    │                    │
                    ▼                    ▼
             Extension / Web UI   insight / summary / actions

Vexa terminal webhook ──► webhook receiver ──► finalizer ──► final REST snapshot
```

### Thành phần source code

```text
backend/
├── app/
│   ├── api/                 # meetings, live stream, webhooks, analysis
│   ├── db/                  # engine, transaction, repositories
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # public Pydantic contracts
│   ├── services/            # Vexa REST/WS, ingest, reconcile, finalizer
│   ├── workers/             # polling, outbox publisher, AI jobs
│   ├── config.py
│   └── main.py
├── migrations/
├── tests/
├── Dockerfile
├── compose.yaml
├── pyproject.toml
└── .env.example
```

## 4. Dữ liệu và tính đúng đắn

| Bảng | Mục đích | Ràng buộc quan trọng |
|---|---|---|
| `meetings` | một lần chạy bot | `vexa_meeting_id UNIQUE` |
| `participants` | speaker identity/display name | `(meeting_id, speaker_key)` |
| `transcript_segments` | transcript draft/final | `UNIQUE(meeting_id, vexa_segment_id)` |
| `incoming_webhooks` | dedupe/audit webhook | `event_id UNIQUE` |
| `outbox_events` | publish đáng tin cậy | `dedupe_key UNIQUE` |
| `analysis_runs` | chống analysis lặp | `(meeting_id, kind, source_revision)` |
| `analysis_results` | summary/actions/evidence | FK `analysis_run_id` |

`native_meeting_id` không là khoá duy nhất của application, vì một room code có thể được dùng ở nhiều lần họp. Dùng application `meeting_id` + `vexa_meeting_id` làm partition key.

### Transcript upsert

Vexa có thể gửi draft, update draft hoặc retract draft trước khi gửi final. Vì vậy:

1. Upsert theo `(meeting_id, vexa_segment_id)`.
2. Nếu text/speaker/time thay đổi: cập nhật row, tăng `revision`, tạo event `transcript.segment.upserted`.
3. `completed=true` tương đương final segment.
4. `transcript_retract` đánh dấu retracted/soft delete rồi phát event retract cho UI.
5. Tất cả update segment và outbox event phải nằm trong cùng database transaction.

## 5. API contract của backend

| Method | Endpoint | Mục đích |
|---|---|---|
| `POST` | `/v1/meetings` | nhận Meet URL, gọi Vexa tạo bot |
| `GET` | `/v1/meetings/{id}` | trạng thái meeting/bot |
| `GET` | `/v1/meetings/{id}/transcript` | snapshot transcript đã chuẩn hoá |
| `POST` | `/v1/meetings/{id}/sync` | REST reconcile thủ công/admin |
| `POST` | `/v1/meetings/{id}/stop` | dừng bot qua backend |
| `GET` | `/v1/meetings/{id}/events` | SSE fallback, có `Last-Event-ID` |
| `WS` | `/v1/meetings/{id}/live` | realtime client events |
| `POST` | `/v1/webhooks/vexa` | private Vexa terminal webhook receiver |
| `POST` | `/v1/meetings/{id}/analysis` | yêu cầu analysis |
| `GET` | `/v1/meetings/{id}/analysis` | live/final results |

Application client event:

```json
{
  "event_id": "01J...",
  "type": "transcript.segment.upserted",
  "meeting_id": "application-uuid",
  "occurred_at": "2026-09-20T10:00:00Z",
  "data": {
    "segment_id": "vexa-segment-id",
    "text": "Nội dung nói",
    "is_final": true
  }
}
```

Browser reconnect gửi cursor (`Last-Event-ID` hoặc `after_event_id`); backend replay event chưa nhận từ outbox/event log rồi mới live fan-out.

## 6. Docker topology và Vexa integration

Backend chạy Compose riêng với PostgreSQL/Redis riêng, nhưng service `backend` gắn thêm vào network Vexa:

```text
backend_default
  ├── backend :8088 (publish localhost only)
  ├── postgres :5432 (internal)
  └── redis :6379 (internal)

vexa-v012_vexa (external network)
  ├── gateway :8000
  ├── meeting-api :8080
  └── backend :8088
```

Không dùng `host.docker.internal` trong integration Docker này: Vexa gateway đang publish host port ở `127.0.0.1`, không bảo đảm container backend gọi được qua host gateway. Backend gọi `http://gateway:8000` trên shared network.

### 6.1 `backend/compose.yaml`

```yaml
services:
  backend:
    build: .
    env_file: .env
    command: uv run uvicorn app.main:app --host 0.0.0.0 --port 8088
    ports: ["127.0.0.1:8088:8088"]
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    networks: [backend, vexa]
    restart: unless-stopped

  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: meeting
      POSTGRES_USER: meeting
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: [backend-postgres:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U meeting -d meeting"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks: [backend]

  redis:
    image: valkey/valkey:8-alpine
    command: ["valkey-server", "--appendonly", "yes"]
    volumes: [backend-redis:/data]
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks: [backend]

networks:
  backend:
  vexa:
    external: true
    name: vexa-v012_vexa

volumes:
  backend-postgres:
  backend-redis:
```

### 6.2 Configuration

`backend/.env.example` chỉ có placeholder:

```dotenv
APP_ENV=development
APP_URL=http://localhost:8088
POSTGRES_PASSWORD=change-me
DATABASE_URL=postgresql+asyncpg://meeting:${POSTGRES_PASSWORD}@postgres:5432/meeting
REDIS_URL=redis://redis:6379/0
VEXA_API_BASE=http://gateway:8000
VEXA_API_KEY=
VEXA_WEBHOOK_SECRET=
JWT_SECRET=
ALLOWED_ORIGINS=http://localhost:3000
```

`backend/.env` chứa secret thật, được `chmod 600`, không commit. `config.py` fail-fast khi production thiếu secret.

## 7. Lộ trình triển khai code

### Phase 1 — Scaffold và persistence

1. Tạo `backend/`, `pyproject.toml`, FastAPI app, Dockerfile, Compose, `.env.example`.
2. Tạo `/health` kiểm tra PostgreSQL/Redis.
3. Thêm SQLAlchemy async + Alembic.
4. Tạo migration cho các bảng ở mục 4.
5. Implement/test repository `create_meeting`, `upsert_segment`, `record_webhook_once`, `enqueue_outbox`.

Pass khi migration chạy trên DB trống, `/health` trả 200, segment và webhook duplicate không tạo row trùng.

### Phase 2 — Vexa REST MVP

1. Implement `VexaClient`: `start_bot`, `get_bot_status`, `get_transcript`, `stop_bot`.
2. Map các lỗi 401/403/404/429/503 sang app exception; không log API key/transcript raw.
3. Implement `POST /v1/meetings`, status, transcript, stop và manual sync.
4. Implement `sync_meeting()` gọi Vexa transcript endpoint, normalize và upsert transactionally.

Pass khi bot Google Meet có thể được tạo qua backend và `POST /sync` lưu transcript vào PostgreSQL.

### Phase 3 — Near-realtime polling + client fan-out

1. Tạo reconcile worker chạy 3 giây/lần cho meeting active.
2. Dùng Redis distributed lock `reconcile:{meeting_id}` để tránh poll trùng khi scale replicas.
3. Implement transactional outbox publisher → Redis Stream/PubSub.
4. Implement SSE `GET /v1/meetings/{id}/events` + replay theo `Last-Event-ID`.

Pass khi segment xuất hiện tại SSE client dưới 5 giây và restart backend không mất transcript sau reconciliation.

### Phase 4 — Vexa WebSocket realtime

1. Kết nối `ws://gateway:8000/ws` với API key chỉ ở backend.
2. Subscribe theo `{platform, native_id}` cho mỗi meeting.
3. Xử lý `transcript`, `transcription_segment`, `transcript_retract`, `meeting.status`, `error`, `pong`.
4. Ping heartbeat, reconnect exponential 1s → 30s, reconcile ngay sau reconnect.
5. Thêm application WebSocket `/v1/meetings/{id}/live` cho Extension/UI.

Pass khi WS latency P95 < 2 giây, reconnect không mất dữ liệu và draft bị retract biến mất ở UI.

### Phase 5 — End-call webhook và finalizer

1. Implement `POST /v1/webhooks/vexa` đọc raw body.
2. Verify timestamp/replay window và HMAC SHA-256 của `timestamp + "." + raw_body`.
3. Dedupe `event_id`; duplicate trả 200, không enqueue lại.
4. Implement finalizer: lock → REST reconcile → retry 2/5/10/20s khi collector flush → mark terminal → enqueue analysis.
5. Bật Vexa system webhook.

Vexa Compose `.env`:

```dotenv
VEXA_SYSTEM_WEBHOOK_URL=http://backend:8088/v1/webhooks/vexa
VEXA_SYSTEM_WEBHOOK_SECRET=<cung-gia-tri-voi-backend-VEXA_WEBHOOK_SECRET>
VEXA_SYSTEM_WEBHOOK_ALLOW_PRIVATE_HTTP=true
VEXA_SYSTEM_WEBHOOK_TIMEOUT_S=10
```

Pass khi một `meeting.completed` delivery lặp lại chỉ tạo một finalization và một final analysis job.

### Phase 6 — Analysis

1. Live worker chỉ dùng finalized segments, debounce 15–30 giây.
2. Final worker chạy sau finalization: summary, decisions, action items, topics và optional risk signal.
3. Lưu `source_revision` và evidence segment IDs cho mọi result.
4. Không xem risk signal là diagnosis y khoa/tâm lý.

Pass khi final run duy nhất tạo summary/action items có evidence truy ngược được.

### Phase 7 — Auth, Extension và hardening

1. JWT/session authentication cho REST/SSE/WS application.
2. AuthZ theo `owner_id`/workspace membership.
3. Extension chỉ gọi backend; nhận SSE/WS; reconnect với cursor.
4. Add metrics/logs, retention/delete meeting, e2e tests.

Pass khi user A không truy cập được meeting user B và Vexa secret không xuất hiện trong client/log/repository.

## 8. Docker runbook

### 8.1 Chạy lần đầu

Vexa và STT phải healthy trước vì backend phụ thuộc network Vexa:

```bash
cd source/vexa/deploy/compose
docker compose ps
curl -fsS http://localhost:18056/health

cd ../transcription
curl -fsS http://localhost:8083/health

cd ../../../../backend
test -f .env || cp .env.example .env
chmod 600 .env
docker network inspect vexa-v012_vexa > /dev/null
docker compose build backend
docker compose run --rm backend uv run alembic upgrade head
docker compose up -d
curl -fsS http://localhost:8088/health
```

### 8.2 Kiểm tra connectivity nội bộ

```bash
cd backend
docker compose exec backend sh -lc 'getent hosts gateway && wget -qO- http://gateway:8000/health'
```

Nếu `gateway` không resolve, lấy đúng tên network bằng `docker network ls`, cập nhật `networks.vexa.name`, sau đó recreate backend:

```bash
docker compose up -d --force-recreate backend
```

### 8.3 Vận hành

```bash
cd backend
docker compose ps
docker compose logs -f backend
docker compose run --rm backend uv run alembic upgrade head
docker compose up -d --build --force-recreate backend
docker compose down     # giữ volumes
```

Không dùng `docker compose down -v` trừ khi chủ động xoá database/Redis backend.

## 9. Testing checklist

| Test | Điều kiện pass |
|---|---|
| DB migration | chạy trên DB trống, rollback/upgrade ổn |
| Segment dedupe | cùng segment ID chỉ còn một row/version |
| Polling | transcript hiện tại client dưới 5 giây |
| Vexa WS reconnect | reconcile khôi phục frame mất |
| Webhook HMAC | signature hợp lệ pass; sai/cũ reject |
| Webhook replay | cùng `event_id` không tạo final job trùng |
| End call | transcript cuối được sync trước analysis |
| AuthZ | user khác không đọc được meeting/transcript |
| E2E | Meet → bot → transcript → backend UI → end-call → final analysis |

## 10. Definition of done

1. User start meeting qua backend; backend gọi Vexa tạo bot.
2. Bot được admit và finalized transcript hiển thị realtime/near-realtime.
3. Backend/WS restart không làm mất transcript sau reconciliation.
4. End-call tạo một final transcript snapshot và đúng một final analysis run.
5. Extension/Web UI hiển thị transcript, summary, action items từ backend.
6. Không có Vexa API key/webhook secret ở browser, logs, response API hay Git.

## 11. Reference documents

- [BACKEND_DESIGN_REALTIME.md](BACKEND_DESIGN_REALTIME.md) — bản thiết kế chuyên sâu gốc.
- [BACKEND_IMPLEMENTATION_PLAN.md](BACKEND_IMPLEMENTATION_PLAN.md) — runbook triển khai chi tiết gốc.
- [CAI_DAT_VEXA_UBUNTU_26.04.md](CAI_DAT_VEXA_UBUNTU_26.04.md) — vận hành Vexa/STT local GPU.
