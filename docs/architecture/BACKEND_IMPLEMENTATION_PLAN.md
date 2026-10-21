# Kế hoạch triển khai Backend Meeting Intelligence

Tài liệu này là runbook triển khai code cho kiến trúc trong [BACKEND_DESIGN_REALTIME.md](BACKEND_DESIGN_REALTIME.md). Mỗi phase kết thúc bằng test và checkpoint. Không triển khai phase sau nếu checkpoint trước chưa đạt.

## 0. Quy ước và ranh giới

### Mục tiêu bản đầu

- Nhận một Google Meet URL từ ứng dụng.
- Gọi Vexa từ backend để tạo/dừng bot.
- Lấy và lưu transcript bền vững.
- Phát transcript near-realtime cho UI/Extension.
- Nhận event kết thúc cuộc gọi, chốt transcript đầy đủ, tạo job phân tích.

### Không làm ở MVP

- Không để Extension gọi Vexa trực tiếp.
- Không đọc Redis/PostgreSQL nội bộ của Vexa.
- Không chạy LLM trên mọi draft segment.
- Không làm Jitsi/Teams/Zoom trước khi Google Meet end-to-end pass.

### Stack

| Layer | Lựa chọn |
|---|---|
| HTTP API | FastAPI + Uvicorn |
| Database | PostgreSQL + SQLAlchemy async + Alembic |
| Queue/realtime fan-out | Redis Streams + Pub/Sub |
| HTTP client / Vexa WS client | `httpx` + `websockets` |
| Worker | asyncio worker trong MVP; tách process khi production |
| Test | pytest + pytest-asyncio + testcontainers hoặc Compose test stack |

## 1. Chuẩn bị project

### 1.1 Tạo cấu trúc

Tạo project tại `backend/`, cạnh `source/vexa/`:

```text
backend/
├── app/
│   ├── api/
│   ├── db/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── workers/
│   ├── main.py
│   └── config.py
├── migrations/
├── tests/
├── Dockerfile
├── compose.yaml
├── pyproject.toml
└── .env.example
```

### 1.2 Khai báo cấu hình

`.env.example` chỉ chứa placeholder:

```dotenv
APP_ENV=development
APP_URL=http://localhost:8088
DATABASE_URL=postgresql+asyncpg://meeting:change-me@postgres:5432/meeting
REDIS_URL=redis://redis:6379/0

VEXA_API_BASE=http://host.docker.internal:18056
VEXA_API_KEY=
VEXA_WEBHOOK_SECRET=

JWT_SECRET=
ALLOWED_ORIGINS=http://localhost:3000
```

`config.py` phải fail-fast khi production thiếu `VEXA_API_KEY`, `VEXA_WEBHOOK_SECRET`, `JWT_SECRET`; không log giá trị secret.

### 1.3 Docker topology và tích hợp Vexa

Chạy backend bằng Compose project riêng, nhưng gắn service `backend` vào **external network** của Vexa. Không dùng `host.docker.internal` cho integration này: Vexa gateway hiện publish về `127.0.0.1` trên host, nên container khác có thể không truy cập được qua host gateway. Network nội bộ cho phép backend gọi trực tiếp `http://gateway:8000`.

Topology:

```text
backend_default
  ├── backend  :8088 (publish ra host)
  ├── postgres :5432 (internal only)
  └── redis    :6379 (internal only)

vexa-v012_vexa (external, do Vexa quản lý)
  ├── gateway      :8000
  ├── meeting-api  :8080
  ├── backend      :8088
  └── các service Vexa khác
```

Với Vexa Compose hiện tại có `COMPOSE_PROJECT_NAME=vexa-v012`, kiểm tra network đã tồn tại:

```bash
docker network inspect vexa-v012_vexa > /dev/null
```

Tạo `backend/compose.yaml` theo skeleton sau (bổ sung khi source code đã tồn tại):

```yaml
services:
  backend:
    build: .
    env_file: .env
    command: uv run uvicorn app.main:app --host 0.0.0.0 --port 8088
    ports:
      - "127.0.0.1:8088:8088"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks: [backend, vexa]
    restart: unless-stopped

  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: meeting
      POSTGRES_USER: meeting
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - backend-postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U meeting -d meeting"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks: [backend]
    restart: unless-stopped

  redis:
    image: valkey/valkey:8-alpine
    command: ["valkey-server", "--appendonly", "yes"]
    volumes:
      - backend-redis:/data
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks: [backend]
    restart: unless-stopped

networks:
  backend:
  vexa:
    external: true
    name: vexa-v012_vexa

volumes:
  backend-postgres:
  backend-redis:
```

Trong `backend/.env`, Vexa API base phải là DNS service nội bộ, không phải URL host:

```dotenv
DATABASE_URL=postgresql+asyncpg://meeting:${POSTGRES_PASSWORD}@postgres:5432/meeting
REDIS_URL=redis://redis:6379/0
VEXA_API_BASE=http://gateway:8000
VEXA_API_KEY=<api-key-cua-Vexa>
VEXA_WEBHOOK_SECRET=<secret-rieng-cho-backend>
```

`POSTGRES_PASSWORD`, Vexa API key và webhook secret phải chỉ có trong `backend/.env` (chmod 600), không commit.

### 1.4 Checkpoint

```bash
cd backend
docker compose up -d postgres redis
uv run uvicorn app.main:app --reload --port 8088
curl -fsS http://localhost:8088/health
```

Pass khi `/health` trả `{"status":"ok"}` và database/Redis connect được.

## 2. Database và migration

### 2.1 Tạo migration đầu tiên

Tạo các bảng sau:

| Bảng | Fields cốt lõi |
|---|---|
| `meetings` | `id UUID`, `owner_id`, `vexa_meeting_id UNIQUE`, `platform`, `native_meeting_id`, `status`, `started_at`, `ended_at`, `finalized_at` |
| `participants` | `id UUID`, `meeting_id FK`, `speaker_key`, `display_name`, `first_seen_at`, `last_seen_at` |
| `transcript_segments` | `id UUID`, `meeting_id FK`, `vexa_segment_id`, `speaker_key`, `speaker_name`, `text`, `start_seconds`, `end_seconds`, `absolute_start_at`, `absolute_end_at`, `is_final`, `revision`, `source` |
| `incoming_webhooks` | `event_id UNIQUE`, `event_type`, `received_at`, `payload JSONB` |
| `outbox_events` | `id UUID`, `dedupe_key UNIQUE`, `event_type`, `aggregate_id`, `payload JSONB`, `published_at` |
| `analysis_runs` | `id UUID`, `meeting_id FK`, `kind`, `source_revision`, `status`, `started_at`, `finished_at` |
| `analysis_results` | `id UUID`, `analysis_run_id FK`, `result JSONB`, `evidence JSONB` |

Ràng buộc quan trọng:

```text
UNIQUE (meeting_id, vexa_segment_id)
INDEX  (meeting_id, absolute_start_at)
INDEX  (meeting_id, is_final)
UNIQUE (event_id) trên incoming_webhooks
```

Không dùng `(platform, native_meeting_id)` làm unique key vì cùng room code có thể xuất hiện ở nhiều lần chạy bot.

### 2.2 Repository layer

Tạo repository methods, tất cả có test:

```text
create_meeting()
set_meeting_status()
upsert_segment()
retract_segments()
list_segments()
record_webhook_once()
enqueue_outbox()
claim_outbox_batch()
```

`upsert_segment()` phải tăng `revision` khi text/speaker/time thay đổi, nhưng không tạo row trùng.

### 2.3 Checkpoint

```bash
uv run alembic upgrade head
uv run pytest tests/db -q
```

Pass khi migration chạy trên database trống và test chứng minh segment/webhook duplicate không tạo row thứ hai.

## 3. Vexa REST client và Meeting API MVP

### 3.1 `services/vexa_client.py`

Định nghĩa interface tách khỏi `httpx`:

```python
async def start_bot(*, platform, native_meeting_id, bot_name, transcribe_enabled) -> VexaMeeting
async def get_bot_status() -> list[VexaBotStatus]
async def get_transcript(platform, native_meeting_id) -> VexaTranscript
async def stop_bot(platform, native_meeting_id) -> None
```

Client phải:

- gửi `X-API-Key` từ server-side config;
- timeout rõ ràng: connect 3s, read 15s;
- map 401/403/404/429/503 sang exception application-specific;
- không log header hay body transcript đầy đủ;
- có fake client cho unit tests.

### 3.2 Endpoints MVP

| Method | Endpoint | Hành vi |
|---|---|---|
| `POST` | `/v1/meetings` | validate Meet URL, lưu row, gọi `VexaClient.start_bot()` |
| `GET` | `/v1/meetings/{id}` | trạng thái application + Vexa |
| `GET` | `/v1/meetings/{id}/transcript` | segments đã lưu trong DB |
| `POST` | `/v1/meetings/{id}/sync` | trigger REST reconcile thủ công (admin/dev) |
| `POST` | `/v1/meetings/{id}/stop` | gọi Vexa stop, đánh dấu `stopping` |

Mọi endpoint lấy `owner_id` từ auth/session, không nhận `owner_id` do client truyền.

### 3.3 Transcript reconciler

Tạo `reconciler.sync_meeting(meeting_id)`:

1. gọi `GET /transcripts/{platform}/{native_meeting_id}`;
2. normalize Vexa `segments` về schema application;
3. upsert mỗi segment và ghi outbox event trong cùng DB transaction;
4. update last-sync timestamp;
5. trả số segment inserted/updated/unchanged.

### 3.4 Checkpoint

- Unit test URL parsing, Vexa error mapping và normalize segment.
- Integration test bằng fake Vexa response gồm pending + confirmed cùng `segment_id`.
- Với Vexa local đang chạy, tạo bot Meet test và `POST /sync` phải lưu transcript vào PostgreSQL.

## 4. Near-realtime bằng polling trước

Polling là milestone trước WebSocket vì dễ debug và cung cấp fallback bắt buộc.

### 4.1 Scheduler

Tạo `workers/reconcile_loop.py`:

- chạy mỗi 3 giây với meeting `active`, `joining`, `awaiting_admission`;
- giới hạn concurrent request bằng semaphore;
- backoff nếu Vexa trả 429/503;
- dừng khi `completed`/`failed`/`finalized`;
- dùng distributed lock Redis `reconcile:{meeting_id}` để nhiều replica không poll trùng.

### 4.2 Fan-out cho client

Outbox publisher:

1. claim batch chưa publish;
2. append Redis Stream `meeting:{id}:events`;
3. publish Redis Pub/Sub `meeting:{id}:live`;
4. set `published_at`.

Client endpoint đầu tiên là SSE:

```text
GET /v1/meetings/{id}/events
```

Hỗ trợ `Last-Event-ID`; khi reconnect replay từ Redis Stream hoặc `outbox_events` trước khi chuyển sang live Pub/Sub.

### 4.3 Checkpoint

- Khi nói trong Meet, segment xuất hiện tại SSE client trong <= 5 giây.
- Restart backend khi meeting active: reconciliation lấy lại transcript bị bỏ lỡ.
- Mở hai client cùng meeting: nhận cùng event nhưng database chỉ có một segment version.

## 5. Vexa WebSocket realtime

Chỉ bắt đầu sau Phase 4 pass; polling vẫn được giữ làm reconciliation.

### 5.1 Kết nối và subscribe

Tạo `services/vexa_ws.py`:

1. kết nối `ws://<vexa-host>/ws` (hoặc `wss://` production) với API key server-side;
2. gửi subscribe payload:

```json
{
  "action": "subscribe",
  "meetings": [{"platform": "google_meet", "native_id": "abc-defg-hij"}]
}
```

3. xử lý `subscribed`, `transcript`, `transcription_segment`, `transcript_retract`, `meeting.status`, `error`, `pong`;
4. heartbeat `{"action":"ping"}`;
5. reconnect exponential backoff 1s → 30s;
6. sau reconnect gọi REST reconciliation ngay.

### 5.2 Normalization rules

- `transcript.confirmed[]`: upsert finalized segments.
- `transcript.pending[]`: upsert draft; UI có thể hiển thị mờ.
- `transcription_segment`: upsert one segment.
- `transcript_retract`: soft-delete hoặc mark retracted, phát event retract.
- `meeting.status`: update state machine application nhưng không suy ra transcript final chỉ từ status.

### 5.3 Checkpoint

- P95 từ Vexa WS frame đến application event < 2 giây trong test room.
- Giết connection backend rồi bật lại: WS reconnect, REST reconciliation sửa mọi khác biệt.
- `transcript_retract` không để draft cũ trên UI.

## 6. End-call webhook và finalization

### 6.1 Vexa configuration

Sau khi webhook receiver đã tồn tại, thêm vào Vexa Compose `.env`:

```dotenv
VEXA_SYSTEM_WEBHOOK_URL=http://<backend-host>:8088/v1/webhooks/vexa
VEXA_SYSTEM_WEBHOOK_SECRET=<secret-rieng>
VEXA_SYSTEM_WEBHOOK_ALLOW_PRIVATE_HTTP=true
VEXA_SYSTEM_WEBHOOK_TIMEOUT_S=10
```

Chạy lại `make all`. `ALLOW_PRIVATE_HTTP=true` chỉ phù hợp backend private/trusted network; production dùng HTTPS + domain private/public đã kiểm soát.

### 6.2 Receiver

`POST /v1/webhooks/vexa` phải thực hiện theo thứ tự:

1. đọc raw bytes trước JSON parsing;
2. verify `X-Webhook-Timestamp` trong time window;
3. verify `X-Webhook-Signature` HMAC-SHA256 của `timestamp + "." + raw_body`;
4. parse envelope;
5. insert `incoming_webhooks` với `event_id UNIQUE`;
6. nếu duplicate, trả `200` không enqueue;
7. enqueue `finalize_meeting` cho `meeting.completed`, `bot.failed`;
8. trả `200` nhanh, không chạy LLM trong HTTP request.

### 6.3 Finalizer

`finalize_meeting()`:

1. distributed lock `finalize:{meeting_id}`;
2. gọi transcript reconcile;
3. retry 2, 5, 10, 20 giây nếu transcript collector còn flush;
4. mark `completed`/`failed`, ghi `finalized_at`;
5. publish `meeting.ended` outbox event;
6. enqueue final analysis.

### 6.4 Checkpoint

- Replay đúng cùng webhook 3 lần: một finalization và một analysis job.
- Dừng bot trong Meet: backend nhận terminal event, transcript cuối lưu được.
- Signature sai hoặc timestamp cũ: trả `401`/`403`, không ghi DB.

## 7. Analysis jobs

### 7.1 Live analysis

Chỉ trigger từ segment finalized; debounce 15–30 giây:

```text
transcript segment finalized
  -> aggregate recent context
  -> lightweight summary/topics/action candidates
  -> analysis_results (kind=live)
  -> outbox ai.analysis.updated
```

### 7.2 Final analysis

Sau finalization:

```text
final transcript snapshot
  -> normalization + participant grouping
  -> summary
  -> decisions
  -> action items {task, owner, deadline, evidence}
  -> topics
  -> optional risk signal {label, score, confidence, evidence}
```

Mỗi result phải lưu `source_revision` và evidence segment IDs. Không trình bày risk signal như chẩn đoán y khoa/tâm lý.

### 7.3 Checkpoint

- Một meeting hoàn thành sinh đúng một final analysis revision.
- Action item có link đến segment evidence.
- Re-run finalizer không tạo action item duplicate.

## 8. Auth, Extension và hardening

### 8.1 AuthZ

- JWT/session auth cho REST, SSE và WebSocket application.
- Query mọi data qua `meeting.owner_id`/workspace membership.
- Không chuyển Vexa key tới browser dưới mọi hình thức.

### 8.2 Chrome Extension integration

1. Extension phát hiện URL Google Meet.
2. Gọi `POST /v1/meetings` bằng user session.
3. Subscribe `WS /v1/meetings/{id}/live` hoặc SSE.
4. Render `segment.upserted`, `segment.retracted`, `meeting.status`, `analysis.updated`.
5. Khi reconnect, gửi cursor `after_event_id`.

### 8.3 Observability

Thêm metrics/logs:

```text
transcript_ingest_lag_seconds
reconcile_duration_seconds
vexa_ws_reconnect_total
webhook_verification_failed_total
meeting_finalization_duration_seconds
analysis_queue_lag_seconds
```

Không đưa raw text transcript hoặc secret vào log mặc định.

### 8.4 Checkpoint production-ready

- Restart bất kỳ backend worker nào không mất transcript sau reconciliation.
- Permission test chứng minh user A không đọc được meeting user B.
- Vexa API key không xuất hiện trong browser network/devtools payload.
- Backup/retention/delete meeting được test.

## 9. Thứ tự commit đề xuất

```text
feat(backend): scaffold FastAPI service and local dependencies
feat(backend): add meeting and transcript persistence
feat(backend): integrate Vexa REST client and transcript reconciliation
feat(backend): stream near-realtime transcript over SSE
feat(backend): ingest Vexa WebSocket transcript frames
feat(backend): finalize meetings from signed Vexa webhooks
feat(backend): add analysis job pipeline
feat(extension): render backend live meeting stream
test(backend): cover reconnect, dedupe, webhook replay, and end-call flow
```

## 10. Docker deploy/runbook sau khi có code

### 10.1 Build và chạy lần đầu

Khởi động Vexa và STT trước; backend phụ thuộc network `vexa-v012_vexa` do Vexa tạo:

```bash
# 1. Vexa control plane và STT phải healthy trước
cd source/vexa/deploy/compose
docker compose ps
curl -fsS http://localhost:18056/health

cd ../transcription
curl -fsS http://localhost:8083/health

# 2. Tạo backend secret file (chỉ lần đầu)
cd ../../../../backend
test -f .env || cp .env.example .env
chmod 600 .env

# 3. Migration chạy bởi backend release command hoặc migration job riêng
docker compose build backend
docker compose run --rm backend uv run alembic upgrade head
docker compose up -d
docker compose ps
curl -fsS http://localhost:8088/health
```

Không chạy `docker compose down -v` trong backend trừ khi chủ động xoá database và Redis application.

### 10.2 Kiểm tra DNS nội bộ Vexa

Backend container phải resolve được service `gateway` trong external network:

```bash
cd backend
docker compose exec backend sh -lc 'getent hosts gateway && wget -qO- http://gateway:8000/health'
```

Pass khi thấy IP network nội bộ và JSON health Vexa. Nếu `gateway` không resolve:

1. xác nhận `docker network inspect vexa-v012_vexa` thành công;
2. xác nhận tên network bằng `docker network ls`;
3. cập nhật `networks.vexa.name` trong `backend/compose.yaml` cho khớp `COMPOSE_PROJECT_NAME` của Vexa;
4. chạy `docker compose up -d --force-recreate backend`.

### 10.3 Bật end-call webhook

Sau khi endpoint `POST /v1/webhooks/vexa` và HMAC verification có test, cấu hình Vexa bằng đúng hostname Docker của backend:

```dotenv
# source/vexa/deploy/compose/.env
VEXA_SYSTEM_WEBHOOK_URL=http://backend:8088/v1/webhooks/vexa
VEXA_SYSTEM_WEBHOOK_SECRET=<cung-gia-tri-voi-backend-VEXA_WEBHOOK_SECRET>
VEXA_SYSTEM_WEBHOOK_ALLOW_PRIVATE_HTTP=true
VEXA_SYSTEM_WEBHOOK_TIMEOUT_S=10
```

Áp dụng cấu hình mà không xoá Vexa data:

```bash
cd source/vexa/deploy/compose
docker compose up -d --force-recreate meeting-api
docker compose logs --tail=100 meeting-api
```

`ALLOW_PRIVATE_HTTP=true` là cần thiết vì target `backend` là private Docker DNS. Chỉ dùng khi network này được kiểm soát; production public dùng HTTPS/reverse proxy và vẫn giữ HMAC verification.

### 10.4 Lệnh vận hành thường dùng

```bash
# Xem trạng thái backend
cd backend
docker compose ps

# Theo dõi API / worker logs
docker compose logs -f backend

# Chạy migration cho version mới
docker compose run --rm backend uv run alembic upgrade head

# Rebuild/recreate backend mà không đụng DB/Redis volume
docker compose up -d --build --force-recreate backend

# Dừng backend nhưng giữ dữ liệu
docker compose down
```

### 10.5 Smoke test toàn chuỗi Docker

1. `curl http://localhost:8088/health` trả 200.
2. Tạo Google Meet từ backend (`POST /v1/meetings`).
3. Admit Vexa bot và nói vài câu.
4. Kiểm tra `GET /v1/meetings/{id}/transcript` và SSE/WS application nhận segment.
5. Kết thúc/dừng bot.
6. Quan sát `meeting.completed` vào log backend; finalizer chạy REST reconcile.
7. Kiểm tra `analysis_runs`/API analysis có một final run duy nhất.

## 11. Definition of done

Một Google Meet thật đạt yêu cầu khi:

1. User bấm Start trên Extension/UI, backend gửi bot qua Vexa.
2. Bot được admit và transcript finalized xuất hiện ở client trong target latency.
3. Mất/reconnect WebSocket không gây mất transcript sau reconcile.
4. Meeting kết thúc tạo đúng một final snapshot và một final analysis run.
5. UI hiển thị transcript, summary và action items từ backend.
6. Vexa key và webhook secret không xuất hiện ở client hoặc repository.
