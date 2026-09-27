# Kế hoạch khôi phục runtime và nghiệm thu E2E

> Phạm vi: stack mới tại `source/compose.yaml`. Không xóa volume hay transcript trong kế hoạch này.
> 
> Nguyên tắc: không đưa giá trị trong `settings.env` hoặc token vào Git, tài liệu hay log.

> Runbook build/validation thống nhất: [`BUILD_AND_ACCEPTANCE_RUNBOOK.md`](BUILD_AND_ACCEPTANCE_RUNBOOK.md).

## Mục tiêu nghiệm thu

`backend`, `worker`, PostgreSQL, Valkey và dashboard của Compose mới phải chạy ổn định; endpoint `/ready` trả `200`; tạo được một analysis job và worker xử lý được job đó. Sau đó mới chạy demo Google Meet → Vexa → transcript → analysis → dashboard.

## Task 1 — Lập biên bản hiện trạng

- [x] Xác nhận stack mới có `backend` và `worker` restart liên tục.
- [x] Xác định lỗi: PostgreSQL từ chối password của user `meeting`.
- [x] Xác nhận Vexa, transcription, PostgreSQL/Valkey ứng dụng vẫn healthy.
- [x] Xác nhận stack cũ `meeting-intelligence-backend` đang chạy song song.
- [x] Thêm script audit lặp lại được: `source/scripts/runtime-status.sh`.

**Kết quả:** đây là lỗi đồng bộ credential giữa `source/settings.env` và role trong volume PostgreSQL của stack mới, không phải lỗi code FastAPI/worker.

Chạy lại biên bản hiện trạng bất kỳ lúc nào bằng:

```bash
cd source
./scripts/runtime-status.sh
```

## Task 2 — Đồng bộ credential PostgreSQL của stack mới

- [x] Kiểm tra tên service/database/user từ `source/compose.yaml` mà không hiển thị secret.
- [x] Đặt lại password của role PostgreSQL `meeting` theo `POSTGRES_PASSWORD` hiện có trong `source/settings.env`.
- [x] Restart riêng `backend` và `worker`.
- [x] Kiểm tra `docker compose ps` và `/ready`.
- [x] Đóng gói thao tác đồng bộ lặp lại được tại `source/scripts/sync-app-db-password.sh`.

**Tiêu chí đạt:** `backend` không còn restart, `worker` ở trạng thái running, `/ready` trả HTTP 200.

**Lưu ý an toàn:** phương án này chỉ đổi password của role ứng dụng, không xóa database/volume. Không dùng `docker compose down -v` nếu chưa có backup và sự đồng ý rõ ràng.

Khi `POSTGRES_PASSWORD` thay đổi hoặc backend báo `InvalidPasswordError`, chạy:

```bash
cd source
./scripts/sync-app-db-password.sh
docker compose --env-file settings.env restart backend worker
./scripts/verify.sh
```

## Task 3 — Xác minh luồng application nội bộ

- [x] Chạy `source/scripts/verify.sh`.
- [x] Kiểm tra worker kết nối PostgreSQL thành công; container đang running và không có lỗi mới sau lần sửa credential.
- [x] Thêm/chạy `source/scripts/smoke-analysis-pipeline.sh`: tạo fixture tổng hợp tạm thời, yêu cầu analysis qua API, kiểm tra worker xử lý và cleanup bằng UUID chính xác.
- [x] Ghi lại output không chứa PII/secret làm evidence: `PASS: synthetic fixture completed API -> queue -> worker -> analytics API.`

**Tiêu chí đạt:** job được worker xử lý đúng một lần; dashboard và API dùng cùng application database.

**Trạng thái 26/09/2026:** smoke test nội bộ đã pass. Fixture tổng hợp được xóa sau test (`fixture_meetings=0`, `analysis_runs=0`); E2E với Google Meet/Vexa và transcript có consent vẫn thuộc Task 5.

## Task 4 — Cô lập stack legacy

- [x] Gắn nhãn rõ `source/meeting-intelligence-backend/` là legacy trong README và checklist demo.
- [x] Đối chiếu port/container của legacy với stack mới.
- [ ] Sau khi stack mới pass Task 3, xin xác nhận trước khi dừng legacy containers hoặc archive thư mục legacy.

**Tiêu chí đạt:** người demo chỉ dùng URL/Compose của `source/`; không có nhầm lẫn backend, dashboard hay database.

| Thành phần | Stack mới (dùng cho demo) | Legacy (không dùng cho demo) |
| --- | --- | --- |
| Compose | `source/compose.yaml` | `source/meeting-intelligence-backend/compose.yaml` |
| Backend host port | `127.0.0.1:8089` | `127.0.0.1:8088` |
| Dashboard host port | `127.0.0.1:3001` | `127.0.0.1:3000` |
| Container backend | `meeting-intelligence-backend-1` | `meeting-intelligence-backend-backend-1` |

**Quy ước hiện tại:** chỉ dùng `http://127.0.0.1:8089/ready` và `http://127.0.0.1:3001/` cho stack mới. Legacy vẫn giữ chạy để không làm gián đoạn dữ liệu hiện có; chỉ dừng sau khi có xác nhận.

## Task 5 — Nghiệm thu E2E với Vexa

- [ ] Tạo Google Meet test có consent.
- [ ] Tạo bot qua API application, admit bot và sync transcript finalized.
- [ ] Yêu cầu final analysis; kiểm tra evidence, timeline, coverage và `unknown` trên dashboard.
- [ ] Thử sync lặp, restart worker và reconnect dashboard.
- [ ] Lưu ảnh/log đã che thông tin nhạy cảm.

**Tiêu chí đạt:** hoàn thành luồng Google Meet → Vexa → PostgreSQL → worker → dashboard và có bằng chứng lặp lại được.

## Task 6 — Độ bền trước khi nộp

- [ ] Bổ sung test integration cho password/readiness, idempotency analysis run, revision/retract và Redis pending-message recovery.
- [ ] Bổ sung reclaim cho Redis Stream pending messages (`XAUTOCLAIM` hoặc chiến lược tương đương) để worker crash không làm kẹt job `running`.
- [ ] Commit riêng thay đổi Vexa đã rút gọn, kèm kiểm thử/ghi chú phạm vi.

**Tiêu chí đạt:** các claim trong luận văn có test/log E2E tương ứng.
