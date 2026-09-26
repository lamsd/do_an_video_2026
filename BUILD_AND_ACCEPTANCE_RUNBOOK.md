# Build lại và nghiệm thu MVP Meeting Intelligence

> Cập nhật: 26/09/2026  
> Phạm vi chốt: **Google Meet → Vexa → Meeting Intelligence → Dashboard**.  
> Không đưa Jitsi, Chrome Extension, Ollama hoặc PhoBERT fine-tune vào đường găng trước khi MVP E2E pass.

## 1. Đánh giá tổng thể

| Hạng mục | Hiện trạng | Quyết định build |
| --- | --- | --- |
| Scope | Blueprint cũ nói Jitsi/Extension, implementation hiện tại dùng Google Meet/Dashboard | Luận văn và demo dùng Google Meet + Vexa; blueprint cũ chỉ là tài liệu tham khảo. |
| Application stack | FastAPI, PostgreSQL, Valkey, worker, dashboard đã chạy | Giữ `source/compose.yaml` là entry point duy nhất. |
| Vexa/STT | Vexa meetings-only và transcription đang chạy | Dùng Vexa như provider bot/transcript; không sửa core Vexa trong giai đoạn demo. |
| AI | `baseline-rules-v1` đã đủ chứng minh pipeline | Không claim PhoBERT/accuracy khi chưa có dataset gán nhãn và report. |
| Runtime | Task 1–3 đã pass, stack legacy vẫn song song | Chỉ dừng legacy sau xác nhận rõ ràng. |
| E2E thật | Chưa chạy bằng Google Meet có consent | Đây là checkpoint bắt buộc tiếp theo. |

## 2. Kiến trúc mục tiêu duy nhất

```text
Google Meet
  → Vexa meeting bot + transcription
  → FastAPI (application ownership, webhook/polling, sync)
  → PostgreSQL (source of truth) + Valkey Stream (queue)
  → sentiment worker (baseline-rules-v1)
  → REST/SSE
  → static Dashboard
```

Nguyên tắc:

- `source/settings.env` là cấu hình runtime local duy nhất; không commit hoặc in secret.
- PostgreSQL application không dùng chung password/volume với PostgreSQL Vexa.
- `source/compose.yaml` là stack demo; `source/meeting-intelligence-backend/` là legacy.
- Transcript thật chỉ dùng khi có consent; fixture tổng hợp chỉ cho smoke test.

## 3. Thứ tự build và checkpoint

### P0 — Chốt scope và bảo vệ dữ liệu

1. Dùng kiến trúc ở Mục 2 trong luận văn, slide và demo.
2. Không chạy `down -v`; backup trước mọi thao tác cần xóa volume.
3. Không commit `source/settings.env`, `source/vexa/deploy/transcription/.env`, transcript, token hoặc log chưa che PII.

**Pass:** scope không mâu thuẫn giữa README, luận văn và demo.

### P1 — Preflight host và cấu hình

```bash
cd source
./scripts/bootstrap.sh
chmod 600 settings.env
./scripts/vexa-selfhost.sh check
docker compose --env-file settings.env config --quiet
```

Kiểm các key không rỗng/placeholder: `POSTGRES_PASSWORD`, `DB_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `ADMIN_TOKEN`, `INTERNAL_API_SECRET`, `VEXA_WEBHOOK_SECRET`. Hai password PostgreSQL phải khác nhau.

**Pass:** Docker Engine/Compose hoạt động, Vexa config valid và Compose config parse thành công.

### P2 — Vexa và transcription

```bash
cd source
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
./scripts/vexa-selfhost.sh status
```

Nếu transcription chưa healthy, sửa riêng `source/vexa/deploy/transcription/.env`, dựng transcription theo README rồi sync URL/token vào `settings.env` bằng `sync-transcription-config`. Không dùng `127.0.0.1` làm URL transcription từ container Vexa.

**Pass:** gateway Vexa healthy, route agent không tồn tại theo chủ ý, transcription reachable từ `meeting-api`.

### P3 — Build stack ứng dụng

```bash
cd source
docker compose --env-file settings.env up -d --build
./scripts/runtime-status.sh
./scripts/verify.sh
```

Nếu backend báo `InvalidPasswordError`, đồng bộ credential không phá dữ liệu:

```bash
./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker
./scripts/verify.sh
```

**Pass:** backend healthy; worker running; PostgreSQL/Valkey healthy; `/ready` và dashboard trả HTTP 200.

### P4 — Xác minh application không dùng dữ liệu thật

```bash
cd source
./scripts/smoke-analysis-pipeline.sh
```

Script tạo dữ liệu tổng hợp tạm thời, kiểm API → queue → worker → analytics và cleanup theo UUID.

**Pass:** in `PASS: synthetic fixture completed API -> queue -> worker -> analytics API.`

### P5 — Cô lập legacy

1. Demo chỉ dùng host port của stack mới do `runtime-status.sh` báo.
2. Chỉ sau khi P1–P4 pass và có xác nhận, dừng stack legacy bằng Compose trong `source/meeting-intelligence-backend/`.
3. Không archive/xóa thư mục legacy cho tới khi có backup và một commit riêng.

**Pass:** không nhầm URL, database hoặc dashboard giữa hai stack.

### P6 — E2E Google Meet có consent

1. Tạo một Google Meet test và nhận consent của người tham gia.
2. Mint/cấu hình API key Vexa nếu chưa có; không đưa key vào browser.
3. Gọi `POST /v1/meetings`, admit bot và nói đoạn tiếng Việt test.
4. Gọi `POST /v1/meetings/{id}/sync`; chỉ tiếp tục khi có segment `is_final=true`.
5. Gọi `POST /v1/meetings/{id}/analysis?kind=final`.
6. Mở Dashboard bằng **application UUID**, không dùng mã Google Meet.
7. Xác nhận overview, timeline, evidence, `unknown`, model version và SSE refresh.

**Pass:** final run `succeeded`, evidence truy ngược transcript/timestamp và dashboard hiển thị đúng database application.

### P7 — Resilience, evidence và luận văn

1. Test sync lặp, revision/retract, worker restart và SSE reconnect.
2. Bổ sung pending-message reclaim cho Redis Stream trước khi claim độ bền worker.
3. Lưu ảnh/log đã che secret/PII: health, Compose, API response, dashboard và protocol môi trường.
4. Chỉ báo cáo chỉ số từ log thật, kèm cỡ mẫu và môi trường chạy.

**Pass:** claim kỹ thuật trong luận văn có test hoặc evidence tương ứng.

## 4. Trạng thái thực tế hiện tại

- P0: scope đã chốt trong tài liệu mới; cần đồng bộ blueprint cũ khi chỉnh luận văn.
- P1–P3: pass trên runtime hiện tại.
- P4: pass bằng synthetic smoke test, fixture đã cleanup.
- P5: đang chờ quyết định dừng legacy.
- P6–P7: chưa thực hiện; là đường găng để nghiệm thu khóa luận.

## 5. Không làm trong giai đoạn build MVP

- Không reset volume (`down -v`) để “sửa nhanh”.
- Không tích hợp Jitsi/Zoom/Teams/Chrome Extension.
- Không fine-tune hoặc tuyên bố kết quả PhoBERT khi chưa có dataset consent, annotation guideline và evaluation report.
- Không đưa token Vexa, password hay raw transcript vào dashboard, Git hoặc evidence.
