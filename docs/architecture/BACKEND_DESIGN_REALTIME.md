# Backend cho transcript realtime và phân tích meeting

## Mục tiêu

Backend là lớp duy nhất giữ Vexa API key, nhận transcript từ Vexa, lưu bền vững, phát dữ liệu cho Chrome Extension/UI và kích hoạt phân tích ở hai thời điểm:

1. **Live / near realtime** — transcript mới xuất hiện trong vài giây khi cuộc họp đang diễn ra.
2. **End-call** — khi bot hoặc meeting kết thúc, lấy transcript đầy đủ, đóng phiên dữ liệu và chạy analysis cuối cùng.

Chrome Extension chỉ gọi backend bằng session/JWT của ứng dụng; **không** biết Vexa API key, URL STT hoặc secret webhook.

## Quyết định transport

| Nhu cầu | Nguồn chính | Fallback / bảo đảm đúng |
|---|---|---|
| Trạng thái bot (`joining`, `active`, `completed`, `failed`) | Vexa WebSocket `/ws`, frame `meeting.status` | `GET /bots/status` hoặc `GET /meetings` theo lịch |
| Transcript live | Vexa WebSocket `/ws`, frame `transcript` hoặc `transcription_segment` | `GET /transcripts/{platform}/{native_meeting_id}` mỗi 3–5 giây khi meeting active |
| Kết thúc cuộc gọi | Vexa system webhook `meeting.completed` / `bot.failed` | poll trạng thái; idempotent finalizer |
| Transcript cuối, có tính chuẩn | `GET /transcripts/{platform}/{native_meeting_id}` | retry ngắn sau terminal event nếu collector còn flush segment |

Không đọc trực tiếp Redis/PostgreSQL nội bộ của Vexa. Đó là implementation detail, không phải integration boundary an toàn.

## Kiến trúc

```text
Google Meet
   │
   ▼
Vexa Bot ── STT local ──► Vexa transcript store
   │                          │
   │                          ├── WebSocket /ws ─► Ingestor ─► PostgreSQL
   │                          │                         │          │
   │                          └── terminal webhook ─► Finalizer ─┘
   │                                                    │
   └────────────────────────────────────────────────────┤
                                                        ▼
                                          Redis Streams / job queue
                                                │                 │
                                                ▼                 ▼
                                      WebSocket gateway       AI workers
                                                │                 │
                                                ▼                 ▼
                                      Extension / web UI    summary/actions
```

## Thành phần backend đề xuất

```text
backend/
├── app/
│   ├── main.py                    # FastAPI, lifespan, routers
│   ├── config.py                  # secret/env validation
│   ├── api/
│   │   ├── meetings.py             # start, status, transcript, stop
│   │   ├── live.py                 # client WebSocket/SSE
│   │   ├── webhooks.py             # Vexa terminal webhook receiver
│   │   └── analysis.py             # request/status/result analysis
│   ├── services/
│   │   ├── vexa_client.py          # REST + reconnecting Vexa WS client
│   │   ├── transcript_ingestor.py  # normalize, dedupe, upsert, outbox
│   │   ├── reconciler.py           # REST snapshot reconciliation
│   │   ├── meeting_finalizer.py    # terminal event -> final transcript -> jobs
│   │   ├── broadcaster.py          # publish to browser clients
│   │   └── webhook_verify.py       # HMAC + anti-replay validation
│   ├── workers/
│   │   ├── live_analysis.py        # debounced rolling insights
│   │   └── final_analysis.py       # summary/actions/topics/risk after end
│   ├── models/                     # SQLAlchemy models
│   └── schemas/                    # Pydantic public/event schemas
├── migrations/
├── tests/
├── Dockerfile
└── compose.yaml
```

FastAPI + PostgreSQL + Redis là stack phù hợp: PostgreSQL giữ dữ liệu/audit lâu dài; Redis Streams hoặc queue đảm bảo các jobs và client fan-out không làm chậm nhận transcript.

## Luồng dữ liệu

### 1. Bắt đầu meeting

1. Extension gọi `POST /v1/meetings` của backend với Meet URL.
2. Backend xác thực người dùng, parse URL, tạo `meetings` row với trạng thái `requested`.
3. Backend gọi `POST /bots` của Vexa với `transcribe_enabled: true`.
4. Lưu `vexa_meeting_id`, `platform`, `native_meeting_id` từ response.
5. Vexa WS ingestor subscribe meeting:

```json
{
  "action": "subscribe",
  "meetings": [{"platform": "google_meet", "native_id": "abc-defg-hij"}]
}
```

6. Backend phát `meeting.status` về client; UI hiện “bot đang xin vào” rồi “live”.

### 2. Transcript live

1. Vexa gửi frame `transcript` (bundle `pending`/`confirmed`) hoặc `transcription_segment`.
2. Ingestor chuẩn hoá mỗi segment thành bản ghi application-owned.
3. Segment được upsert theo `(meeting_id, vexa_segment_id)`:
   - `pending` là draft, có thể update/retract;
   - `completed=true` là finalized;
   - update không tạo thêm một dòng transcript trùng.
4. Cùng transaction, ghi một `outbox_event` (`transcript.segment.upserted`).
5. Publisher đọc outbox, publish Redis Stream và gửi event cho WS client.
6. Live-analysis worker nhận segment finalized, gom theo cửa sổ 15–30 giây rồi chạy insight nhẹ. Không chạy LLM cho từng từ/draft.

### 3. Reconciliation

WebSocket là latency path, không phải source of truth duy nhất. Worker chạy 3–5 giây/lần cho mỗi meeting active:

```text
GET /transcripts/google_meet/{native_meeting_id}
```

So sánh/upsert snapshot trả về. Điều này khôi phục frame mất khi Vexa WS hoặc backend reconnect, và đóng các draft chưa được push đúng lúc. Dừng polling khi meeting terminal.

### 4. End-call

Vexa gửi webhook `meeting.completed` hoặc `bot.failed`. Webhook **at-least-once**, do đó:

1. Verify chữ ký HMAC trên raw body.
2. Chống replay qua timestamp window (ví dụ ±5 phút).
3. Insert `incoming_webhook(event_id UNIQUE, raw_body, received_at)`.
4. Nếu `event_id` đã tồn tại: trả `200` ngay, không chạy lại.
5. Enqueue `finalize_meeting(vexa_meeting_id)`.
6. Finalizer gọi REST transcript snapshot; retry exponential (ví dụ 2, 5, 10, 20 giây) khi transcript/segment cuối chưa flush.
7. Đánh dấu meeting `completed`/`failed`, dừng poller, phát event `meeting.ended`.
8. Enqueue final analysis: summary, decisions, action items, topics, risk signals.

## Bảng dữ liệu tối thiểu

| Bảng | Khóa/chỉ mục quan trọng | Vai trò |
|---|---|---|
| `meetings` | `id`, `vexa_meeting_id UNIQUE`, `(platform,native_meeting_id)` | một lần chạy bot, trạng thái, thời gian |
| `participants` | `(meeting_id, speaker_key)` | ánh xạ speaker stable/display name |
| `transcript_segments` | `UNIQUE(meeting_id, vexa_segment_id)` | text, thời gian, speaker, draft/final, revision |
| `incoming_webhooks` | `event_id UNIQUE` | webhook idempotency/audit |
| `outbox_events` | `id`, `dedupe_key UNIQUE`, `published_at` | reliable publish sau DB transaction |
| `analysis_runs` | `(meeting_id, kind, source_revision)` | tránh chạy analysis trùng |
| `analysis_results` | `analysis_run_id` | summary/actions/topics/risk và evidence |

`native_meeting_id` không đủ để định danh duy nhất lịch sử: một phòng Meet có thể dùng lại. Luôn ưu tiên `vexa_meeting_id`/application `meeting_id` làm partition key.

## Hợp đồng API của backend

| Endpoint | Mục đích |
|---|---|
| `POST /v1/meetings` | tạo Vexa bot từ Meet URL |
| `GET /v1/meetings/{id}` | trạng thái ứng dụng + bot |
| `GET /v1/meetings/{id}/transcript` | snapshot transcript đã chuẩn hoá |
| `POST /v1/meetings/{id}/stop` | dừng bot qua backend |
| `GET /v1/meetings/{id}/events` | SSE fallback cho client không có WebSocket |
| `WS /v1/meetings/{id}/live` | event live: status, segment upsert/retract, insight |
| `POST /v1/webhooks/vexa` | private receiver của Vexa system webhook |
| `POST /v1/meetings/{id}/analysis` | yêu cầu analysis thủ công |
| `GET /v1/meetings/{id}/analysis` | kết quả live/final analysis |

Mỗi event client có envelope ổn định:

```json
{
  "event_id": "01J...",
  "type": "transcript.segment.upserted",
  "meeting_id": "uuid",
  "occurred_at": "2026-09-20T10:00:00Z",
  "data": {"segment_id": "...", "text": "...", "is_final": true}
}
```

Client reconnect gửi `Last-Event-ID` (SSE) hoặc `after_event_id` (WS subscribe); backend replay từ `outbox_events`/event log rồi mới live fan-out. Vì vậy reconnect không bỏ transcript.

## Cấu hình Vexa cho end-call webhook

Vexa system webhook hiện được source giới hạn ở `meeting.completed` và `bot.failed`. Đặt URL backend chỉ sau khi backend đã có endpoint verify HMAC. Với backend chạy cùng Docker host/private network, cần opt-in explicit:

```dotenv
# source/vexa/deploy/compose/.env
VEXA_SYSTEM_WEBHOOK_URL=http://<backend-host>:8080/v1/webhooks/vexa
VEXA_SYSTEM_WEBHOOK_SECRET=<secret-rieng-cho-webhook>
VEXA_SYSTEM_WEBHOOK_ALLOW_PRIVATE_HTTP=true
VEXA_SYSTEM_WEBHOOK_TIMEOUT_S=10
```

Không dùng IP/URL public không bảo vệ. Không log raw transcript hoặc bất cứ credential nào.

## Bảo mật và vận hành

- `VEXA_API_KEY` và `VEXA_SYSTEM_WEBHOOK_SECRET` chỉ ở backend secret store; browser không nhận chúng.
- Verify `X-Webhook-Timestamp` và `X-Webhook-Signature` bằng HMAC SHA-256 của `timestamp + "." + raw_body`.
- Retain `event_id` webhook ít nhất 48 giờ để dedupe retry của Vexa.
- Đặt auth/ACL theo workspace/meeting cho tất cả REST, WS và transcript export.
- Encrypt database volumes/backups; có retention/delete endpoint theo meeting.
- Structured logs chỉ chứa `request_id`, `meeting_id`, `segment_id`, latency và status; không log text transcript mặc định.
- Metrics: WS reconnects, segment lag, reconcile lag, webhook failures, finalization duration, analysis queue lag.

## Thứ tự triển khai

1. **MVP capture:** schema PostgreSQL, `vexa_client`, `POST /meetings`, REST poller, snapshot transcript.
2. **Near realtime:** Vexa WS ingestor, segment upsert, application WS/SSE cho UI, reconnect + reconciliation.
3. **End-call reliable:** webhook verifier, idempotency table, finalizer và final transcript snapshot.
4. **Analysis:** queue/outbox, rolling summary và final summary/action extraction.
5. **Extension:** detect Meet URL, gọi backend, render event stream; không giao tiếp Vexa trực tiếp.

## Acceptance criteria

- Segment mới có mặt tại client trong mục tiêu P95 < 5 giây khi WS healthy.
- Sau khi backend reconnect, REST reconciliation xoá chênh lệch transcript trong < 15 giây.
- Một `meeting.completed` delivery lặp lại không tạo analysis hoặc action items trùng.
- Transcript sau end-call được snapshot đầy đủ trước khi final analysis chạy.
- API key Vexa và webhook secret không xuất hiện trong extension, log, response API hay repository.
