# Tài liệu tổng hợp — Meeting Intelligence MVP

> Cập nhật: 26/09/2026  
> Nguồn hợp nhất: runbook Crossnote, `source/README.md`, `source/SELFHOST_CONFIGURATION.md`, `RUNTIME_RECOVERY_TASKS.md`, `BUILD_AND_ACCEPTANCE_RUNBOOK.md` và mã nguồn hiện tại.

## 1. Mục tiêu và phạm vi chốt

Hệ thống phân tích **sắc thái của transcript cuộc họp**, không suy luận sức khỏe tâm thần, tính cách hoặc đánh giá con người.

Luồng MVP:

```text
Google Meet → Vexa bot + transcription → FastAPI
           → PostgreSQL + Valkey Stream → sentiment worker
           → REST/SSE → Dashboard
```

Phạm vi demo/khóa luận:

- Nền tảng: Google Meet qua Vexa.
- Nhãn: `positive`, `neutral`, `negative`, `unknown`.
- Model hiện tại: `baseline-rules-v1`, chỉ để xác minh pipeline; không phải PhoBERT đã được benchmark.
- PostgreSQL là source of truth; Valkey phục vụ queue/realtime.
- Dashboard dùng application UUID, không dùng mã phòng Google Meet.

Ngoài phạm vi trước khi MVP E2E hoàn thành: Jitsi, Zoom, Teams, Chrome Extension, Ollama, fine-tune PhoBERT và triển khai production/HA.

## 2. Trạng thái đã xác minh

| Hạng mục | Trạng thái |
| --- | --- |
| Vexa meetings-only gateway | Healthy |
| Transcription runtime | Đang chạy |
| Stack mới: backend/PostgreSQL/Valkey/dashboard | Healthy |
| Stack mới: worker | Running |
| `/ready` và dashboard | Pass |
| Smoke test API → queue → worker → analytics | Pass với fixture tổng hợp, auto-cleanup |
| E2E Google Meet + transcript có consent | Chưa chạy |
| Stack legacy | Vẫn đang chạy song song, không dùng để demo |

Port hiện tại:

| Thành phần | Stack mới — dùng cho demo | Legacy — không dùng cho demo |
| --- | --- | --- |
| Backend | `http://127.0.0.1:8089` | `http://127.0.0.1:8088` |
| Dashboard | `http://127.0.0.1:3001` | `http://127.0.0.1:3000` |

## 3. Cấu trúc project

```text
source/
├── compose.yaml                 # Entry point duy nhất của stack mới
├── settings.env                 # Cấu hình local/secret, không commit
├── src/backend/                 # FastAPI, worker, tests
├── src/dashboard/               # Dashboard tĩnh qua Nginx
├── scripts/                     # Build, audit, recovery, smoke test
└── vexa/                        # Vexa meetings-only + transcription
```

`source/meeting-intelligence-backend/` là bản legacy. Không sửa/dùng bản này trong demo mới; chỉ dừng sau khi có xác nhận để tránh gián đoạn dữ liệu hiện có.

## 4. Quy tắc cấu hình và bảo mật

1. Chỉ dùng `source/settings.env` cho runtime; không commit file này.
2. `POSTGRES_PASSWORD` dành cho application; `DB_PASSWORD` dành cho Vexa. Hai giá trị phải khác nhau.
3. Dùng `VEXA_COMPOSE_PROJECT_NAME=vexa-meetings`; **không** thêm `COMPOSE_PROJECT_NAME` vào `settings.env`.
4. Application gọi Vexa qua `VEXA_API_BASE=http://gateway:8000` và network `vexa-meetings_vexa`.
5. `VEXA_API_KEY`, password, webhook secret, raw transcript và PII không xuất hiện trong Dashboard, Git hay evidence.
6. `TRANSCRIPTION_SERVICE_URL` phải truy cập được từ container Vexa; không dùng `127.0.0.1` nếu transcription chạy trên Docker host.
7. Không chạy `docker compose down -v` trừ khi đã backup và chấp nhận xóa volume tương ứng.

## 5. Build và kiểm chứng theo thứ tự

### Bước 1 — Preflight cấu hình

```bash
cd source
./scripts/bootstrap.sh
chmod 600 settings.env
./scripts/vexa-selfhost.sh check
docker compose --env-file settings.env config --quiet
```

**Pass:** hiện `Configuration is valid.` và Compose parse thành công.

### Bước 2 — Vexa và transcription

```bash
cd source
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh status
./scripts/vexa-selfhost.sh verify
```

Nếu cần đồng bộ endpoint/token transcription từ file local mà không in token:

```bash
HOST_LAN_IP=<IP_LAN_HOST> ./scripts/vexa-selfhost.sh sync-transcription-config
```

**Pass:** gateway healthy; Vexa services cần thiết running/healthy; transcription reachable.

### Bước 3 — Build stack application

```bash
cd source
docker compose --env-file settings.env up -d --build
./scripts/runtime-status.sh
./scripts/verify.sh
```

**Pass:** backend healthy, worker running, `/ready` và dashboard trả HTTP 200.

Nếu gặp `InvalidPasswordError` cho role application:

```bash
./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker
./scripts/verify.sh
```

Lệnh này chỉ đồng bộ password role ứng dụng; không xóa database hay volume.

### Bước 4 — Smoke test nội bộ

```bash
cd source
./scripts/smoke-analysis-pipeline.sh
```

Script tạo fixture tổng hợp, chạy API → Redis Stream → worker → analytics, sau đó xóa fixture theo UUID chính xác.

**Pass:**

```text
PASS: synthetic fixture completed API -> queue -> worker -> analytics API.
```

### Bước 5 — E2E Google Meet có consent

1. Tạo một Google Meet test và có consent người tham gia.
2. Nếu chưa có key Vexa, chạy `./scripts/vexa-selfhost.sh mint-token`, sau đó dán token vào `VEXA_API_KEY` trong `settings.env` — không log/token commit.
3. Tạo meeting qua API:

```bash
curl --fail --show-error -X POST http://127.0.0.1:8089/v1/meetings \
  -H 'Content-Type: application/json' \
  -H 'X-App-User-Id: local-dev' \
  -d '{"meeting_url":"https://meet.google.com/<room-code>","bot_name":"Meeting Assistant"}'
```

4. Lưu `id` trả về làm `<MEETING_ID>`, admit bot và nói một số câu tiếng Việt.
5. Sync transcript:

```bash
curl --fail --show-error -X POST http://127.0.0.1:8089/v1/meetings/<MEETING_ID>/sync \
  -H 'X-App-User-Id: local-dev'

curl --fail --show-error http://127.0.0.1:8089/v1/meetings/<MEETING_ID>/transcript \
  -H 'X-App-User-Id: local-dev'
```

6. Chỉ tiếp tục khi có ít nhất một segment `is_final=true`; transcript rỗng thường thuộc capture/STT upstream.
7. Chạy final analysis:

```bash
curl --fail --show-error -X POST 'http://127.0.0.1:8089/v1/meetings/<MEETING_ID>/analysis?kind=final' \
  -H 'X-App-User-Id: local-dev'
```

8. Mở `http://127.0.0.1:3001`, nhập `<MEETING_ID>`, kiểm overview, timeline, coverage, `unknown`, evidence, model version và refresh SSE.

**Pass:** final run `succeeded`; evidence có transcript/timestamp và Dashboard phản ánh đúng database application.

## 6. Checklist trước demo

- [ ] `./scripts/runtime-status.sh` báo stack mới healthy.
- [ ] `./scripts/vexa-selfhost.sh verify` pass.
- [ ] `./scripts/smoke-analysis-pipeline.sh` pass.
- [ ] Chỉ dùng port stack mới `8089`/`3001`.
- [ ] Meeting test có consent và bot được admit.
- [ ] Có transcript finalized trước khi yêu cầu final analysis.
- [ ] Dashboard dùng application UUID đúng.
- [ ] Log/ảnh đã che secret, PII và raw transcript không cần thiết.

## 7. Việc cần hoàn thiện trước khi nộp

1. Chạy E2E thật và lưu evidence có timestamp.
2. Test retry, sync lặp, revision/retract, worker restart, SSE reconnect.
3. Thêm reclaim cho Redis Stream pending messages để worker crash không kẹt job `running`.
4. Bổ sung test integration cho webhook, idempotency và authorization.
5. Đồng bộ luận văn với implementation: baseline-rules, quality gate, limitation và kết quả đo thật.
6. Commit riêng thay đổi rút gọn trong Vexa sau khi kiểm thử.

## 8. Tài liệu liên quan

- [Build & acceptance runbook](../operations/BUILD_AND_ACCEPTANCE_RUNBOOK.md)
- [Recovery task checklist](../operations/RUNTIME_RECOVERY_TASKS.md)
- [Technical backlog for thesis](../thesis/THESIS_IMPLEMENTATION_TASK_BREAKDOWN.md)
- [Application README](../../source/README.md)
- [Self-host configuration](../../source/SELFHOST_CONFIGURATION.md)
