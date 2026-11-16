# Đánh giá tính khả thi triển khai thực tế — Meeting Intelligence

> **Snapshot lịch sử:** audit này đóng băng trạng thái Google Meet/baseline v2 ngày
> 31-10-2026. Nó không mô tả runtime demo/UAT hiện tại. Đối chiếu với
> [Project master guide](PROJECT_MASTER_GUIDE.md) và
> [kiến trúc Jitsi--Vexa--STT](../architecture/JITSI_VEXA_STT_RUNTIME_ARCHITECTURE.md)
> trước khi dùng bất kỳ kết luận hay checklist nào bên dưới.

> Ngày đánh giá: 31-10-2026 (Asia/Ho_Chi_Minh)
> Vai trò đánh giá: PM / Giám đốc dự án
> Phạm vi: `source/compose.yaml`, backend mới trong `source/src/backend`, Dashboard, Vexa meetings-only, cấu hình runtime hiện hữu và tài liệu vận hành.
> Không thực hiện thay đổi cấu hình, dữ liệu hay chạy Google Meet thật trong đợt đánh giá này.

## 1. Quyết định điều hành

**Quyết định hiện tại: NO-GO cho triển khai production hoặc cho người dùng bên ngoài.**

Hệ thống đã chứng minh được phần khung kỹ thuật nội bộ: Docker Compose hợp lệ, backend/Dashboard/Vexa gateway khởi động được và unit test backend chạy qua. Tuy nhiên, sản phẩm chưa chứng minh được luồng giá trị chính với người dùng thật: Google Meet → bot → transcription → transcript → analysis → Dashboard.

Mức phù hợp hiện tại:

| Mức sử dụng | Quyết định | Điều kiện |
| --- | --- | --- |
| Demo kiến trúc nội bộ, dữ liệu tổng hợp | **Có điều kiện** | Không dùng để tuyên bố chất lượng sentiment. |
| Pilot retrospective nội bộ, có consent | **Chưa đạt** | Phải khôi phục STT, sửa timestamp/retraction, hoàn thành E2E và kiểm soát dữ liệu. |
| Production/public/ra quyết định về con người | **Không đạt** | Chưa có authentication, model validation, retention, backup/restore và vận hành production. |

## 2. Bằng chứng đã kiểm tra

| Hạng mục | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `docker compose --env-file settings.env config --quiet` | Pass | Compose parse được. |
| Backend `/ready` và Dashboard | Pass | PostgreSQL, Valkey, backend và Dashboard hiện truy cập được trên loopback. |
| Vexa `check` và `verify` | Pass | Gateway meetings-only và bot image sẵn sàng. |
| Backend pytest | 23 tests pass | Chỉ là test đơn vị/logic chọn lọc, không thay thế integration/E2E. |
| Ruff | Fail 3 lỗi import/noqa trong trainer TF-IDF | Chưa đạt trạng thái lint sạch. |
| Health của transcription service | **Fail — connection refused** | Bot hiện không có dependency STT sẵn sàng để tạo transcript thật. |
| `VEXA_WEBHOOK_URL` | Trống | Auto-finalize qua public webhook chưa vận hành; hiện phải sync/final thủ công. |
| Google Meet E2E có consent | Chưa có evidence pass | Đây là gate quan trọng nhất còn thiếu. |
| Model runtime | `rules` / `baseline-rules-v2` | Là baseline kiểm pipeline, không phải model đã benchmark. |

## 3. Lỗi và rủi ro đang tồn tại

### P0 — Chặn pilot hoặc production

#### P0.1. Transcription service không kết nối được

- **Bằng chứng:** health request tới endpoint STT đã cấu hình trả `connection refused`.
- **Tác động:** bot có thể vào Google Meet nhưng không tạo transcript; toàn bộ giá trị sản phẩm phía sau không hoạt động.
- **Cần làm:** xác nhận process STT chạy, firewall/LAN route, URL truy cập được từ container Vexa, token đúng; sau đó chạy Google Meet E2E có consent.
- **Điều kiện đóng lỗi:** Vexa container gọi được `STT_URL/health`, bot tạo segment final và application lưu được segment đúng `meeting_id`.

#### P0.2. Authentication/authorization chưa tồn tại

File [`auth.py`](../../source/src/backend/app/auth.py) chấp nhận trực tiếp `X-App-User-Id` làm owner. Bất kỳ client nào gửi header đều có thể mạo danh user; môi trường production chỉ từ chối khi header bị thiếu, không xác thực giá trị header.

- **Tác động:** lộ transcript/evidence, truy cập chéo meeting, stop bot hoặc yêu cầu analysis trái phép nếu API được public.
- **Cần làm:** thay bằng OIDC/JWT hoặc session đã xác minh; xác lập workspace/role/meeting membership ở server; rate-limit và audit log.
- **Điều kiện đóng lỗi:** test chứng minh user A không thể đọc/stop/request analysis cho meeting của user B dù tự đặt header bất kỳ.

#### P0.3. Timestamp của timeline/evidence có thể bị sai

Vexa cho phép `start/end` là offset theo thời điểm bắt đầu cuộc họp hoặc epoch. Vexa còn trả `absolute_start_time`; nhưng ứng dụng lưu `start/end` rồi luôn xử lý chúng như UNIX epoch.

- Nguồn Vexa: [`adapters.py`](../../source/vexa/core/meetings/services/meeting-api/src/meeting_api/collector/adapters.py) giải thích hai semantics của timestamp.
- Ứng dụng: [`units.py`](../../source/src/backend/app/analysis/units.py) gọi trực tiếp `datetime.fromtimestamp`.
- **Tác động:** evidence có thể hiển thị năm 1970 hoặc bucket phút không đúng thực tế; timeline mất giá trị audit.
- **Cần làm:** ưu tiên `absolute_start_time`; nếu chỉ có offset thì anchor theo `meeting.started_at`/thời điểm do Vexa trả; lưu rõ semantic và thêm test cả hai trường hợp.

#### P0.4. Không xử lý transcript retraction/xoá segment

[`service.py`](../../source/src/backend/app/service.py) chỉ upsert segment hiện diện trong snapshot. Segment đã bị Vexa retract hoặc không còn trong snapshot không bị đánh dấu `retracted=True`, dù schema đã có trường này.

- **Tác động:** unit, KPI và evidence có thể dùng câu STT cũ/sai; audit trail không còn đúng nguồn.
- **Cần làm:** lấy tập `segment_id` trong snapshot, mark segment cũ thiếu khỏi snapshot là retracted theo contract; phát outbox event, tăng revision và re-run analysis.
- **Điều kiện đóng lỗi:** test upsert → retraction → analysis mới không còn text đã rút.

### P1 — Rủi ro nghiêm trọng trước pilot mở rộng

#### P1.1. Retry/reclaim queue chưa hoàn chỉnh

`ANALYSIS_MAX_RETRIES` được cấu hình nhưng không được sử dụng để retry. Worker đánh dấu run là `failed`; lần request tiếp theo nhận lại chính run cũ vì `get_or_create_run` trả mọi run đã tồn tại, gồm cả run failed.

- **Tác động:** lỗi tạm thời ở DB/Redis/model khiến final analysis bị kẹt failed cho cùng revision/model.
- **Cần làm:** thiết kế trạng thái retryable, exponential backoff, giới hạn attempt, delayed reclaim Redis pending entries và thao tác requeue được kiểm soát.
- **Điều kiện đóng lỗi:** kill worker hoặc ngắt Redis trong lúc chạy; job tự hồi phục đúng policy, không duplicate prediction.

#### P1.2. Health check không chứng minh worker còn xử lý được job

Worker không có Docker healthcheck. `/ready` của backend chỉ kiểm PostgreSQL và Valkey; Dashboard có thể xanh khi worker không còn tiêu thụ queue.

- **Tác động:** false-green, phát hiện muộn khi analysis treo.
- **Cần làm:** worker heartbeat/last-success metric, healthcheck riêng, queue lag và alert khi job queued/running quá ngưỡng.

#### P1.3. Docker socket và thay đổi cấu hình qua browser

`operator-runner` mount Docker socket và project directory, sau đó nhận request từ backend để ghi `settings.env` và recreate container.

- **Tác động:** không được public; một lỗi authorization hoặc SSRF có thể trở thành rủi ro host-level. UI còn nói secret “không gửi qua browser” nhưng vẫn có trường nhập Vexa API key.
- **Cần làm:** loại runner/Docker socket khỏi production compose; chuyển thao tác secret sang CLI/secret manager; nếu giữ local dev, tách dev override và validate mọi giá trị cấm newline/`.env` injection.
- **Điều kiện đóng lỗi:** compose production không còn socket/runner; dashboard không có input secret.

#### P1.4. Chưa có data lifecycle và disaster recovery

Transcript, analysis unit, prediction, outbox payload và webhook payload được lưu; chưa có endpoint/workflow retention, xoá theo consent, backup/restore drill, RTO/RPO, alert hay dashboard observability.

- **Tác động:** không đáp ứng yêu cầu vận hành dữ liệu hội họp nhạy cảm; mất dữ liệu hoặc không thể thực hiện quyền xoá.
- **Cần làm:** data inventory, retention matrix, purge job có audit, backup riêng app PostgreSQL và Vexa PostgreSQL/MinIO; kiểm restore trên môi trường tách biệt.

#### P1.5. Model baseline không đủ cho use case nghiệp vụ

`baseline-rules-v2` chỉ dò một số từ khoá; khi số keyword positive/negative bằng nhau, kể cả không có keyword, nó gán `neutral` confidence 0.70.

- **Tác động:** không có cơ sở để diễn giải sentiment thực tế, càng không được dùng cho HR, đánh giá học tập hoặc sức khoẻ tâm thần.
- **Cần làm:** corpus transcript meeting đã consent, nhãn `negative/neutral/positive`, split theo `meeting_id`, benchmark locked test, calibration và model card.

### P2 — Chất lượng release, tài liệu và quản trị dự án

1. Nhiều tài liệu còn ghi `baseline-rules-v1`, trong khi runtime là `baseline-rules-v2`; cần đồng bộ README, runbook và luận văn.
2. Worktree có thay đổi chưa commit. Có file untracked `source/tmpxs854e_1`, không bị ignore, cùng kích thước với `settings.env`; phải xem là **nguy cơ chứa secret** cho đến khi xác minh, xoá an toàn và rotate secret nếu cần.
3. Corpus legacy liên quan `tram_cam`/depression đang nằm trong Git. Dù tài liệu đã quarantine hợp lý, cần review license, provenance, mức nhạy cảm và tránh đưa raw text vào release/public repository.
4. Image tags Compose chưa pin digest; chưa có release tag/image digest/CI gate tái lập.
5. SSE đọc toàn bộ outbox của meeting mỗi giây, không có retention hay cursor thực sự; sẽ không phù hợp tải lớn.

## 4. Kế hoạch khắc phục theo thứ tự

### Trong 24–48 giờ

- [ ] Khôi phục STT và kiểm thử từ đúng network Vexa.
- [ ] Chạy một Google Meet test có consent; lưu evidence đã redaction: bot admitted, transcript final, final analysis `succeeded`, Dashboard đúng meeting UUID.
- [ ] Đóng/giới hạn Dashboard ở `127.0.0.1`; không public API khi chưa có auth.
- [ ] Kiểm tra và xử lý `source/tmpxs854e_1`; không commit, không in nội dung secret; rotate credential nếu file từng được copy/chia sẻ.
- [ ] Sửa lint trainer để CI không xanh giả.

### Sprint kỹ thuật kế tiếp

- [ ] Sửa relative/absolute timestamp và retraction; thêm integration test contract Vexa.
- [ ] Hoàn thiện retry/reclaim, idempotency và worker health/queue lag.
- [ ] Thay identity header bằng authentication/authorization thật.
- [ ] Tách operator-runner và Docker socket khỏi cấu hình production.
- [ ] Chuẩn hoá tài liệu/model version và tạo release tag tái lập.

### Trước pilot có người dùng thật

- [ ] Consent form, dữ liệu nào thu thập, ai truy cập, thời hạn lưu, quy trình xoá.
- [ ] Backup/restore drill pass cho hai domain dữ liệu: application và Vexa.
- [ ] Monitoring/alert cho STT, bot lifecycle, API error, queue lag, failed run, storage capacity.
- [ ] Load/restart test; đo latency, throughput và giới hạn số meeting đồng thời.
- [ ] UAT với operator: hiểu đúng `unknown`, coverage và giới hạn diễn giải kết quả.

## 5. Checklist đánh giá tính khả thi ứng dụng thực tế

### A. Nhu cầu và phạm vi

- [ ] Một use case rõ ràng, ưu tiên retrospective sau họp; không dùng để chấm điểm con người.
- [ ] Có product owner, đối tượng dùng, tiêu chí thành công và quyết định được phép/không phép dựa vào output.
- [ ] Có ước tính chi phí bot/STT/compute/storage theo meeting và ngân sách được duyệt.

### B. Luồng kỹ thuật đầu-cuối

- [ ] STT health pass từ Vexa network.
- [ ] Bot join/admit/leave Google Meet ổn định.
- [ ] Transcript final, speaker attribution, revision, retraction và timestamp được xác minh.
- [ ] Webhook hợp lệ/tampered/replay đều có test; polling fallback hoạt động.
- [ ] Restart backend/worker không mất hoặc duplicate job.
- [ ] Load test theo số meeting đồng thời và độ dài meeting thực tế.

### C. Model và chất lượng dữ liệu

- [ ] Data card: nguồn, license/consent, redaction, thời hạn lưu, provenance.
- [ ] Annotation guideline; ít nhất hai annotator, adjudication và inter-annotator agreement.
- [ ] Train/validation/test không leakage theo `meeting_id` lẫn text.
- [ ] Báo cáo Macro-F1, F1 từng lớp, confusion matrix, calibration, coverage và error analysis trên locked test.
- [ ] Threshold `unknown` được chọn trên validation, không chọn sau khi nhìn test.
- [ ] Model card nói rõ limitation, nhóm ngôn ngữ/domain không hỗ trợ và prohibited use.

### D. Security và privacy

- [ ] SSO/JWT/session, RBAC workspace/meeting và audit log.
- [ ] TLS, secure headers, rate-limit, secret manager và key rotation.
- [ ] Không còn Docker socket/secret input trên browser trong production.
- [ ] Retention, export/delete workflow được test trên dữ liệu mẫu.
- [ ] Evidence/log/CI không chứa transcript thô, PII hoặc credential.

### E. Vận hành và khôi phục

- [ ] Worker healthcheck, queue lag, alert và dashboard quan sát vận hành.
- [ ] Image digest pinning, SBOM/dependency scan, CI test/lint/migration gate.
- [ ] Backup và restore drill được ký nhận; RTO/RPO được xác định.
- [ ] Runbook incident: STT down, Vexa down, Redis pending, DB restore, secret leak.
- [ ] Rollback deployment đã diễn tập và có owner chịu trách nhiệm.

## 6. Tiêu chí GO cho pilot hẹp

Chỉ chuyển sang pilot retrospective có consent khi toàn bộ điều kiện sau đạt:

1. STT và E2E Google Meet pass ít nhất ba lần độc lập.
2. Timestamp, retraction, retry/restart được test pass.
3. Không public service; chỉ operator đã được phân quyền sử dụng.
4. Consent, retention và xoá dữ liệu được xác nhận bằng quy trình thực thi.
5. Dashboard hiển thị rõ model version, coverage, unknown và cảnh báo “không đánh giá con người”.
6. Kết quả được mô tả là **thử nghiệm vận hành/pipeline**, không phải độ chính xác sentiment, cho đến khi có benchmark hợp lệ.

## 7. Kết luận

Dự án có nền tảng kiến trúc tốt cho khóa luận và demo kỹ thuật: tách database ứng dụng, queue, evidence, version model và Dashboard là hướng hợp lý. Tuy vậy, hiện tại giá trị sản phẩm cốt lõi chưa được chứng minh trên luồng thực, và các gate security/data/ops chưa đạt.

Ưu tiên quyết định không phải thêm PhoBERT hay tính năng mới. Thứ tự đúng là: **khôi phục transcription → chứng minh E2E → sửa đúng dữ liệu thời gian/retraction → bảo vệ truy cập và dữ liệu → chứng minh model bằng benchmark hợp lệ**.
