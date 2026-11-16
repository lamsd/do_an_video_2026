# Checklist Jitsi E2E: bot → transcript → phân tích → dashboard

> Phạm vi: đường demo/UAT hiện hành **Jitsi Meet → Vexa → STT local → Meeting
> Intelligence → Dashboard**. Checklist này không khẳng định chất lượng ASR,
> dịch máy, sentiment hay quyền truy cập production.

## Trước khi tạo bot

1. Thông báo cho mọi người trong phòng và nhận consent trước khi bot xử lý audio
   hoặc transcript. Không đưa audio, transcript, token hoặc ảnh chưa che dữ liệu
   vào Git/chat/evidence public.
2. Kiểm runtime cục bộ:

   ```bash
   cd /home/lamsd/Documents/Buildkhoaluan/source
   ./scripts/runtime-status.sh
   ./scripts/verify.sh
   ./scripts/vexa-selfhost.sh verify
   ```

   `backend`/`worker` phải running, `/ready` phải trả `200`, gateway Vexa và
   transcription service phải healthy. Nếu smoke test chưa pass, chạy
   `./scripts/smoke-analysis-pipeline.sh` trước; smoke test dùng fixture tổng hợp,
   không kiểm chứng bot thật.
3. Tạo hoặc vào một phòng Jitsi, ví dụ `https://meet.jit.si/TenPhongCuaBan`, và
   giữ host ở trong phòng. Nếu phòng dùng password, lobby hoặc policy riêng, host
   xử lý quyền đó trong Jitsi; dashboard không có quyền bypass.

## Tạo bot từ Dashboard

1. Mở Dashboard tại `http://127.0.0.1:<DASHBOARD_PORT>` (runtime hiện tại có thể
   dùng port `3001`) và hard refresh bằng `Ctrl+Shift+R`.
2. Trong **Bắt đầu cuộc họp mới**, dán URL Jitsi đầy đủ, nhập tên bot và chọn:
   `Tiếng Việt` cho cuộc họp tiếng Việt, `Tiếng Anh` cho tiếng Anh, hoặc `Tự nhận
   diện` khi có lý do chạy họp đa ngôn ngữ.
3. Tick xác nhận consent rồi bấm **Yêu cầu bot tham gia**. Lưu Application Meeting
   UUID do dashboard trả về; không dùng tên phòng Jitsi làm UUID.
4. Mở danh sách participant trong Jitsi và xác nhận bot xuất hiện. Khi bot chưa
   xuất hiện, **không tạo request thứ hai** cho cùng phòng trong khi request đầu
   vẫn `requested`, `joining` hoặc `active`.

Nút dashboard chỉ gửi request. Bot xuất hiện trong phòng và có segment final là
hai điều kiện quan sát riêng, không suy diễn từ thông báo ``đã tạo meeting''.

## Tạo bot qua API (khi cần chẩn đoán)

Chỉ dùng API từ máy cục bộ; không dán Vexa API key vào lệnh này.

```bash
curl --fail --show-error -X POST http://127.0.0.1:${API_PORT:-8088}/v1/meetings \
  -H 'Content-Type: application/json' \
  -H 'X-App-User-Id: local-dev' \
  -d '{"meeting_url":"https://meet.jit.si/TenPhongCuaBan","bot_name":"Meeting Assistant","transcription_language":"vi"}'
```

Ghi lại trường `id` trả về dưới dạng `<MEETING_ID>`. Request lặp cùng owner/phòng
đang hoạt động phải trả lại meeting hiện có thay vì spawn bot trùng.

## Kiểm transcript và phân tích

1. Nói vài câu rõ ràng bằng ngôn ngữ đã chọn, tránh nhạc/video nền. Chờ Vexa/STT
   tạo segment final.
2. Đồng bộ và kiểm segment:

   ```bash
   curl --fail --show-error -X POST \
     http://127.0.0.1:${API_PORT:-8088}/v1/meetings/<MEETING_ID>/sync \
     -H 'X-App-User-Id: local-dev'

   curl --fail --show-error \
     http://127.0.0.1:${API_PORT:-8088}/v1/meetings/<MEETING_ID>/transcript \
     -H 'X-App-User-Id: local-dev'
   ```

   Chỉ tạo analysis khi có ít nhất một segment `is_final=true`. Segment bị quality
   gate loại vẫn có thể hiện trong chế độ audit, nhưng không được đưa vào KPI/timeline.
3. Trên Dashboard bấm **Chạy lại phân tích**, hoặc gọi:

   ```bash
   curl --fail --show-error -X POST \
     'http://127.0.0.1:${API_PORT:-8088}/v1/meetings/<MEETING_ID>/analysis?kind=final' \
     -H 'X-App-User-Id: local-dev'
   ```

4. Mở `<MEETING_ID>` trên Dashboard và kiểm: trạng thái run `succeeded`, revision,
   `baseline-rules-v3`, coverage, quality reason, evidence và refresh SSE. Kết quả
   sentiment chỉ mô tả text đạt điều kiện; không phải bản dịch máy, chẩn đoán hoặc
   đánh giá con người.

## Khi bot hoặc dữ liệu không xuất hiện

Kiểm theo thứ tự để không che mất nguyên nhân gốc:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
docker compose --env-file settings.env ps
docker compose --env-file settings.env logs --tail=120 backend worker
./scripts/vexa-selfhost.sh status
./scripts/verify.sh
```

- Bot không có trong participant list: kiểm URL Jitsi, host còn trong phòng,
  password/lobby/policy của phòng và trạng thái Vexa; không retry liên tục.
- Bot có mặt nhưng transcript rỗng: kiểm health/endpoint/token của STT, audio thực
  sự vào bot và log transcription. Không tạo segment giả để làm dashboard có dữ liệu.
- Transcript có nhưng KPI rỗng: mở audit quality reasons, kiểm language routing,
  revision/run status và log worker.
- Lỗi `connection reset`/`502`: lưu timestamp và log đã redaction, kiểm gateway/STT
  trước khi recreate service. Không dùng `docker compose down -v` như bước sửa lỗi.

## Evidence tối thiểu

Lưu cục bộ một bundle đã redaction gồm thời điểm, commit/image digest, command,
exit code, trạng thái health, Application Meeting UUID nếu được phép lưu, run ID,
revision, coverage và ảnh dashboard đã che transcript/PII. Không lưu password,
token, audio hay raw transcript. Kiến trúc và giới hạn chi tiết được mô tả tại
[JITSI_VEXA_STT_RUNTIME_ARCHITECTURE.md](../architecture/JITSI_VEXA_STT_RUNTIME_ARCHITECTURE.md).
