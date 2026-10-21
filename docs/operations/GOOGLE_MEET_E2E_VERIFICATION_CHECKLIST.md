# Kịch bản chạy từng bước: Google Meet → Transcript → AI → Dashboard

> Mục tiêu: tự build lại toàn bộ stack, tạo một cuộc họp Google Meet có bot Vexa,
> xác nhận transcript vào đúng database ứng dụng, chạy sentiment analysis và kiểm
> tra kết quả trên Dashboard.
>
> Phạm vi stack hiện hành: `source/compose.yaml` + `source/src/backend/`.
> **Không dùng `source/meeting-intelligence-backend/`** vì đây là bản legacy.
>
> Mỗi lệnh trong tài liệu này chạy ở một dòng riêng trong **cùng một terminal**,
> trừ khi hướng dẫn nói khác. Không viết `MEETING_ID=... curl ...` trên cùng một
> dòng vì biến có thể không được shell mở rộng như mong đợi.

## 0. Tiêu chí pass cuối cùng

Một lần kiểm tra được xem là pass khi tất cả điều kiện sau đúng:

- Backend, worker, PostgreSQL, Valkey và Dashboard đều healthy.
- Bot Vexa vào được Google Meet test sau khi được host admit.
- `transcript_segments` của application PostgreSQL có segment của đúng `meeting_id`.
- Một `analysis_run` có `kind=final` và `status=succeeded`.
- Dashboard hiển thị `Model = baseline-rules-v1`, KPI, timeline và evidence.
- Có thể truy từ một evidence trên Dashboard về transcript và timestamp trong DB.

## 1. Chuẩn bị và an toàn dữ liệu

1. Chỉ dùng Google Meet test và phải có sự đồng ý của người tham gia trước khi
   bot ghi nhận transcript.
2. Không đưa `settings.env`, API key, password, raw transcript hoặc ảnh chứa PII
   vào Git/luận văn.
3. Không chạy `docker compose down -v`; lệnh đó xóa volume database.
4. Nếu legacy stack vẫn chạy, giữ nguyên nhưng **không dùng port/DB của nó** cho
   kịch bản này. Stack mới luôn lấy port từ `settings.env`; không tự đoán port.

Mở terminal tại thư mục gốc dự án:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
```

## 2. Kiểm tra cấu hình trước build

Xác nhận file runtime tồn tại và chỉ kiểm tra tên biến (không in giá trị secret):

```bash
test -f settings.env
cut -d= -f1 settings.env | sed '/^[[:space:]]*#/d;/^[[:space:]]*$/d' | sort
chmod 600 settings.env
```

Các biến bắt buộc cho đường chạy này:

| Nhóm | Biến cần kiểm tra |
| --- | --- |
| App DB | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` |
| App/Vexa | `VEXA_API_BASE`, `VEXA_API_KEY`, `VEXA_NETWORK`, `VEXA_MODE` |
| AI | `MODEL_VERSION`, `SENTIMENT_CONFIDENCE_THRESHOLD`, `POLL_INTERVAL_SECONDS` |
| Vexa self-host | `DB_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `ADMIN_TOKEN`, `INTERNAL_API_SECRET` |

Kiểm tra các host port của Vexa là số hợp lệ. Đặc biệt, dòng này phải chính xác:

```dotenv
RUNTIME_API_PORT=18190
```

Không để ký tự thừa, ví dụ `RUNTIME_API_PORT=18190z`, vì Docker Compose sẽ báo
`invalid hostPort` và Vexa không nhận cấu hình mới.

Kiểm tra cấu hình và Vexa self-host:

```bash
./scripts/bootstrap.sh
./scripts/vexa-selfhost.sh check
docker compose --env-file settings.env config --quiet
```

**Pass:** không có lỗi parse Compose, secret bắt buộc không còn `CHANGE_ME`, và
`VEXA_API_KEY` đã được cấu hình. Không dùng API key trên browser.

### Kiểm tra bắt buộc: transcription service

Bot chỉ tạo transcript khi endpoint STT hoạt động. Kiểm tra endpoint đang cấu hình
trước khi tạo Google Meet:

```bash
STT_URL=$(awk -F= '$1 == "TRANSCRIPTION_SERVICE_URL" { print $2; exit }' settings.env)
test -n "$STT_URL"
curl --fail --silent --show-error --max-time 5 "$STT_URL/health"
```

**Pass:** `/health` trả HTTP 200. Nếu không kết nối được, khởi động service tại
máy GPU/CPU đang chạy transcription, hoặc sửa `TRANSCRIPTION_SERVICE_URL` thành
LAN IP/hostname mà container Vexa có thể truy cập. Token `API_TOKEN` tại
`vexa/deploy/transcription/.env` phải khớp `TRANSCRIPTION_SERVICE_TOKEN` trong
`settings.env`; sau khi đổi token/URL, chạy `./scripts/vexa-selfhost.sh start`
để Vexa nhận cấu hình mới.

Ví dụ nếu transcription chạy trên chính máy có IP LAN `192.168.1.239`:

```bash
HOST_LAN_IP=192.168.1.239 ./scripts/vexa-selfhost.sh sync-transcription-config
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
curl --fail --silent --show-error http://192.168.1.239:8083/health
```

## 3. Khởi động Vexa và application stack

Khởi động phần Vexa trước:

```bash
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
```

Sau đó build application:

```bash
docker compose --env-file settings.env up -d --build
./scripts/runtime-status.sh
./scripts/verify.sh
docker compose --env-file settings.env ps
```

**Pass:** `backend`, `worker`, `postgres`, `valkey`, `dashboard` đều running/healthy;
`verify.sh` báo backend `/ready` và Dashboard reachable.

Đồng bộ password PostgreSQL cho worker ngay sau lần dựng đầu tiên hoặc sau khi đổi
`POSTGRES_PASSWORD`. Lệnh này chỉ đổi password role, không xóa database/volume:

```bash
./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker
docker compose --env-file settings.env logs --since=2m --tail=80 worker
./scripts/verify.sh
```

**Pass:** log mới của worker không có `InvalidPasswordError`. Không dùng
`logs --tail=30` để kết luận vì lệnh đó có thể hiển thị traceback cũ trước restart.

## 4. Xác nhận pipeline bằng dữ liệu tổng hợp (không bắt buộc nhưng nên chạy)

```bash
./scripts/smoke-analysis-pipeline.sh
```

**Pass:** xuất hiện `PASS: synthetic fixture completed API -> queue -> worker -> analytics API.`
Script tự xóa fixture sau khi chạy; không dùng kết quả fixture để báo cáo demo thật.

## 5. Tạo Google Meet và gọi backend tạo bot

1. Tạo một Google Meet test trên trình duyệt và giữ màn hình host mở.
2. Sao chép URL đầy đủ, ví dụ `https://meet.google.com/abc-defg-hij`.
3. Lấy port API từ `settings.env` và gọi backend. Thay `MEET_URL` bằng URL thực,
   không để URL thật trong file Markdown/commit. In `API_BASE` trước để tránh lỗi
   curl `URL rejected: No host part in the URL`.

```bash
API_PORT=$(awk -F= '$1 == "API_PORT" { print $2; exit }' settings.env)
API_PORT=${API_PORT:-8088}
API_BASE="http://127.0.0.1:${API_PORT}"
echo "$API_BASE"

MEET_URL='https://meet.google.com/abc-defg-hij'

curl --fail --silent --show-error \
  -X POST "${API_BASE}/v1/meetings" \
  -H 'Content-Type: application/json' \
  -H 'X-App-User-Id: local-dev' \
  -d "{\"meeting_url\":\"${MEET_URL}\",\"bot_name\":\"Meeting Assistant\"}"
```

Lưu `id` UUID trong response vào biến `MEETING_ID`. Đây là **application meeting ID**;
không phải mã phòng Google Meet.

```bash
MEETING_ID='<uuid từ response POST /v1/meetings>'
curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${API_BASE}/v1/meetings/${MEETING_ID}"
```

4. Quay lại Google Meet, admit bot khi Google Meet yêu cầu.
5. Chờ bot vào phòng và được admit. Bật mic của người tham gia thật, nói liên tục
   15–20 giây bằng tiếng Việt rõ ràng, rồi dừng nói. Ví dụ: “Cảm ơn mọi người,
   phần này rất tốt. Hiện tại có lỗi nên tiến độ đang khó khăn.”
6. Chờ **35–45 giây sau khi dừng nói**. Máy hiện chạy STT
   `large-v3-turbo` trên CPU nên cần thời gian đóng đoạn audio và inference.

**Pass:** bot xuất hiện trong Meet và endpoint trạng thái trả đúng UUID/meeting.

## 6. Đồng bộ và kiểm tra transcript qua API

Sau khi đã chờ theo Mục 5, sync thủ công:

```bash
curl --fail --silent --show-error \
  -X POST "${API_BASE}/v1/meetings/${MEETING_ID}/sync" \
  -H 'X-App-User-Id: local-dev'

curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${API_BASE}/v1/meetings/${MEETING_ID}/transcript"
```

**Pass:** response sync có `changed > 0` và `total > 0`; transcript có text, timestamp, speaker (nếu
Vexa trả về) và ít nhất một segment `is_final: true`.

Nếu `total=0`, kiểm tra lần lượt:

```bash
docker compose --env-file settings.env logs --tail=100 backend
./scripts/vexa-selfhost.sh status
```

Nguyên nhân thường là bot chưa được admit, mic của người nói đang mute, bot chưa
nhận audio, STT/transcription chưa healthy hoặc chưa chờ đủ lâu; không phải lỗi model.

Đọc log bot đang hoạt động để phân biệt capture và STT:

```bash
docker ps --format '{{.Names}}' | grep '^vexa-mtg-'
docker logs --tail=150 <ten-container-vexa-mtg>
```

- Log `AUDIO ... emitted=...` nghĩa là bot đã nhận audio.
- Log chỉ có `silent`/`emitted=0` nghĩa là chưa có audio từ Google Meet; kiểm tra
  admit, mic và nói lại trước khi sync.
- Log `STT DEGRADED`, `STT-FAULT`, `401`, `400` hoặc `fetch failed` nghĩa là kiểm
  tra lại URL/token transcription ở Mục 2.

Nếu bot đã vào Meet và log có `stt unavailable`, `401`, `400` hoặc `fetch failed`,
dừng test hiện tại và quay lại kiểm tra `/health` ở Mục 2. Không chạy analysis cho
meeting có `total=0`; sau khi sửa STT, tạo một meeting mới để có phiên nghiệm thu
sạch.

## 7. Kiểm tra database ứng dụng

Các lệnh dưới đây chỉ đọc dữ liệu. `postgres` ở đây là PostgreSQL của application,
không phải database control-plane của Vexa.

```bash
docker compose --env-file settings.env exec -T postgres \
  psql -U meeting -d meeting -P pager=off \
  -c "SELECT id, owner_id, vexa_meeting_id, platform, native_meeting_id, status, transcript_revision, created_at, ended_at, finalized_at FROM meetings WHERE id = '${MEETING_ID}'::uuid;"

docker compose --env-file settings.env exec -T postgres \
  psql -U meeting -d meeting -P pager=off \
  -c "SELECT vexa_segment_id, speaker_name, language, start_seconds, end_seconds, is_final, retracted, revision, left(text, 120) AS text_preview FROM transcript_segments WHERE meeting_id = '${MEETING_ID}'::uuid ORDER BY start_seconds;"
```

| Bảng | Ý nghĩa cần kiểm |
| --- | --- |
| `meetings` | Một meeting application, ID Vexa, trạng thái và `transcript_revision` |
| `transcript_segments` | Transcript đã sở hữu bởi application; mỗi segment có final/revision |
| `outbox_events` | Event transcript/analysis phát cho SSE |
| `analysis_runs` | Lịch sử job phân tích và version model |
| `analysis_units` | Văn bản đã quality-gate/gộp trước khi inference |
| `sentiment_predictions` | Nhãn, confidence, probabilities của từng unit |
| `meeting_sentiment_windows` | Dữ liệu nhanh cho KPI/timeline |

**Pass:** `meetings.id` đúng `MEETING_ID`, `transcript_segments` có dữ liệu vừa nói
và `transcript_revision` tăng khi transcript thay đổi.

## 8. Kết thúc họp và chạy final analysis

Kết thúc Google Meet hoặc dừng bot từ backend. Với demo local, chạy sync cuối và
request final analysis để không phụ thuộc webhook public:

```bash
curl --fail --silent --show-error \
  -X POST "${API_BASE}/v1/meetings/${MEETING_ID}/sync" \
  -H 'X-App-User-Id: local-dev'

curl --fail --silent --show-error \
  -X POST "${API_BASE}/v1/meetings/${MEETING_ID}/analysis?kind=final" \
  -H 'X-App-User-Id: local-dev'
```

Theo dõi đến khi `status` là `succeeded`:

```bash
while true; do
  curl --fail --silent --show-error \
    -H 'X-App-User-Id: local-dev' \
    "${API_BASE}/v1/meetings/${MEETING_ID}/analysis"
  sleep 2
done
```

Nhấn `Ctrl+C` sau khi thấy run mới nhất có `"kind":"final"` và `"status":"succeeded"`.
Nếu `failed` hoặc chờ quá 60 giây, lấy log:

```bash
docker compose --env-file settings.env logs --tail=150 worker backend
```

## 9. Kiểm tra model đang chạy và kết quả trong DB

Model hiện tại được lấy từ `MODEL_VERSION` trong `settings.env`. Giá trị mặc định
trong template là `baseline-rules-v1`: classifier luật deterministic để kiểm chứng
pipeline, **không phải PhoBERT** và không được dùng để tuyên bố metric chất lượng model.

```bash
grep '^MODEL_VERSION=' settings.env

docker compose --env-file settings.env exec -T postgres \
  psql -U meeting -d meeting -P pager=off \
  -c "SELECT id, kind, source_revision, model_version, preprocessing_version, status, attempt, metrics, error_code, started_at, finished_at FROM analysis_runs WHERE meeting_id = '${MEETING_ID}'::uuid ORDER BY created_at DESC;"

docker compose --env-file settings.env exec -T postgres \
  psql -U meeting -d meeting -P pager=off \
  -c "SELECT u.speaker_name, left(u.text, 120) AS unit_preview, u.quality_status, p.label, p.confidence, p.probabilities FROM analysis_units u LEFT JOIN sentiment_predictions p ON p.analysis_unit_id = u.id WHERE u.meeting_id = '${MEETING_ID}'::uuid ORDER BY u.start_at;"
```

Diễn giải:

- `quality_status=accepted`: unit được đưa vào classifier.
- `quality_status=rejected`: transcript vẫn được lưu để audit nhưng không tạo kết luận sentiment.
- `label=unknown`: dữ liệu/model không đủ tin cậy; đây là kết quả hợp lệ.
- `metrics.coverage`: tỷ lệ analysis unit được chấp nhận, không phải accuracy của model.

## 10. Thao tác trên Dashboard

1. Lấy port Dashboard từ `settings.env`, in URL rồi mở đúng URL đó. Ví dụ runtime
   hiện tại dùng Dashboard `3001` và API `8089`; port `3000`/`8088` có thể là
   legacy stack.

```bash
DASHBOARD_PORT=$(awk -F= '$1 == "DASHBOARD_PORT" { print $2; exit }' settings.env)
DASHBOARD_PORT=${DASHBOARD_PORT:-3000}
echo "http://127.0.0.1:${DASHBOARD_PORT}"
```

2. Nếu UI báo `API 502` trong khi `${API_BASE}/ready` trả `200`, Dashboard đang
   giữ Docker DNS/IP cũ của backend sau khi backend được recreate. Restart riêng
   Dashboard (không làm mất dữ liệu), sau đó tải lại trang:

```bash
docker compose --env-file settings.env restart dashboard
```

3. Refresh Dashboard. Dashboard tự gọi `GET /v1/meetings?limit=1`, chọn meeting mới
   nhất của user hiện tại, tải transcript và giữ SSE connection để refresh khi có
   event transcript/analysis. Không cần nhập `MEETING_ID` trong luồng demo thông thường.
4. Chỉ nhập **`MEETING_ID` UUID** khi muốn xem một meeting cũ thay vì meeting mới
   nhất; không nhập mã phòng Google Meet.
5. Bấm “Chạy phân tích cuối” sau khi Mục 6 pass.
6. Kiểm tra các thành phần:

| Thành phần UI | Kết quả mong đợi |
| --- | --- |
| Status | `Analysis succeeded` và revision phù hợp |
| Model | `baseline-rules-v1` (hoặc chính xác `MODEL_VERSION` đã cấu hình) |
| Positive / Neutral / Negative | Tỷ trọng các prediction đã aggregate |
| Coverage | Có thể < 100% vì quality gate loại noise/segment ngắn |
| Polarity | `[-1, 1]` hoặc “Không đủ dữ liệu” |
| Timeline | Các cửa sổ theo phút có score/coverage |
| Evidence | Speaker, text, label, confidence, timestamp và quality status |
| Transcript trực tiếp | Số segment và text được refresh khi Vexa sync transcript mới |

Đối chiếu evidence với DB/API:

```bash
curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${API_BASE}/v1/meetings/${MEETING_ID}/analytics/overview"

curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${API_BASE}/v1/meetings/${MEETING_ID}/analytics/timeline"

curl --fail --silent --show-error \
  -H 'X-App-User-Id: local-dev' \
  "${API_BASE}/v1/meetings/${MEETING_ID}/analytics/units"
```

**Pass:** model/version, status, evidence text và timestamp trên Dashboard khớp dữ
liệu API/DB của cùng `MEETING_ID`.

## 11. Evidence cần lưu cho báo cáo/demo

Lưu ảnh hoặc output đã che thông tin nhạy cảm của:

1. `docker compose ps` và `/ready`.
2. Response `POST /v1/meetings` chỉ với UUID/metadata cần thiết.
3. Kết quả sync: số `total`, `changed`, status; không công khai raw transcript.
4. `analysis_runs`: `model_version`, status, coverage và thời gian.
5. Dashboard KPI, timeline và evidence đã che tên/ngữ liệu nhạy cảm.

Không diễn giải `baseline-rules-v1` như một model PhoBERT hay kết quả đánh giá
sentiment có độ chính xác đã được benchmark. Để claim PhoBERT cần artifact model,
dataset consent/gán nhãn và evaluation report riêng.

## 12. Bảng ghi kết quả một lần chạy

| Hạng mục | Kết quả | Ghi chú |
| --- | --- | --- |
| Thời điểm chạy |  |  |
| Google Meet có consent | ☐ Pass / ☐ Fail |  |
| Vexa/transcription healthy | ☐ Pass / ☐ Fail |  |
| Backend + worker + DB + dashboard healthy | ☐ Pass / ☐ Fail |  |
| Application `MEETING_ID` |  | Không ghi URL Meet thật |
| Transcript final trong DB | ☐ Pass / ☐ Fail | Số segments:  |
| `analysis_runs.status=succeeded` | ☐ Pass / ☐ Fail |  |
| `model_version` |  |  |
| Dashboard khớp API/DB | ☐ Pass / ☐ Fail |  |
| Evidence đã che PII | ☐ Pass / ☐ Fail |  |
| Lỗi/phát hiện cần xử lý |  |  |
