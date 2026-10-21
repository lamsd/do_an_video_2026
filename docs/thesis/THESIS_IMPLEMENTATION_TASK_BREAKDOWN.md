# Phân rã công việc hoàn thiện khóa luận

> Cập nhật: 21/09/2026  
> Căn cứ: [`NEXT_STEPS_TO_COMPLETE_THESIS.md`](NEXT_STEPS_TO_COMPLETE_THESIS.md), [`AI_SENTIMENT_ANALYSIS_DASHBOARD_PLAN.md`](../ai-data/AI_SENTIMENT_ANALYSIS_DASHBOARD_PLAN.md) và mã nguồn MVP tại `source/meeting-intelligence-backend/`.

## 1. Mục tiêu và nguyên tắc thực hiện

Hoàn thiện một MVP phân tích **sắc thái của transcript cuộc họp**, có thể chạy xuyên suốt từ Google Meet + Vexa đến dashboard. Mục tiêu chính là chứng minh kiến trúc, tính ổn định, khả năng truy vết và khả năng vận hành; không công bố độ chính xác PhoBERT khi chưa có tập đánh giá và log thực nghiệm kiểm chứng.

Phạm vi bản nộp:

- Nền tảng bắt buộc: Google Meet thông qua Vexa.
- Nhãn MVP: `positive`, `neutral`, `negative`, `unknown`; `unknown` không được gộp vào `neutral`.
- Kết quả phải truy vết được về transcript, revision, lần chạy và phiên bản model.
- PostgreSQL là nguồn dữ liệu chuẩn; Valkey/Redis chỉ phục vụ queue và fan-out realtime.
- Không suy luận sức khỏe tâm thần, tính cách hay đánh giá con người từ transcript.

## 2. Trạng thái xuất phát

Các hạng mục đã có trong MVP và cần **xác minh/lưu bằng chứng**, không làm lại từ đầu:

- Luồng Vexa active meeting → backend sync → PostgreSQL → Valkey Stream → AI worker → dashboard đã từng chạy local.
- Backend đã có quality gate, analysis unit, baseline rules, analysis API, SSE và dashboard MVP.
- Classifier hiện tại là `baseline-rules-v1`, chỉ dùng để xác minh data contract/pipeline; không mô tả là PhoBERT hoặc mô hình đã được đánh giá.

## 3. Trình tự tổng thể và mốc kiểm soát

```text
P0 Chốt phạm vi
 → P1 Audit dữ liệu/contract
 → P2 Độ bền backend & database
 → P3 Quality gate + baseline
 → P4 API/dashboard/realtime
 → P5 E2E & vận hành
 → P6 Thực nghiệm model (có điều kiện)
 → P7 Viết, rà soát và nộp khóa luận
```

Chỉ chuyển phase khi toàn bộ tiêu chí “Hoàn thành” của phase đó đạt. Mỗi task đóng lại phải có: mã nguồn/tài liệu thay đổi, lệnh kiểm tra đã chạy, kết quả hoặc ảnh chụp/log đã lưu.

## 4. Backlog theo phase

### P0 — Chốt phạm vi, đạo đức và tiêu chí nghiệm thu

**Mục tiêu:** khóa phạm vi để tránh mở rộng sang Zoom/Teams, dashboard đẹp hoặc fine-tune khi lõi chưa đáng tin.

1. [ ] Viết một trang “scope freeze”: Vietnamese-first, 3 nhãn polarity + `unknown`, Google Meet + Vexa là integration bắt buộc.
   - Đầu ra: `docs/SCOPE_AND_ACCEPTANCE.md`.
2. [ ] Chốt định nghĩa `segment`, `analysis unit`, cửa sổ biểu đồ (khởi đầu 60 giây), `coverage`, `unknown`, live/final/backfill run.
   - Đầu ra: bảng thuật ngữ và sơ đồ luồng được cập nhật trong tài liệu thiết kế.
3. [ ] Chốt consent, quyền truy cập transcript, retention và chính sách không dùng kết quả để đánh giá con người.
   - Đầu ra: mục đạo đức/quyền riêng tư cho báo cáo và checklist vận hành.
4. [ ] Chốt tiêu chí demo cuối: một meeting hợp lệ tạo đúng một final run; dashboard hiện KPI, timeline, evidence, trạng thái và `unknown`.
   - Đầu ra: checklist demo có dữ liệu đầu vào và expected result.

**Hoàn thành khi:** thầy hướng dẫn/nhóm thực hiện đồng ý scope; không có claim về độ chính xác model chưa được đo.

### P1 — Audit transcript và chốt data contract

**Mục tiêu:** xác định transcript thực có đủ điều kiện phân tích và cố định contract để tất cả component cùng hiểu dữ liệu.

1. [ ] Chọn transcript đã có quyền sử dụng; tạo tập fixture đã ẩn danh gồm: tiếng Việt, code-switch, segment ngắn/rỗng, lặp, revision, retract, thiếu speaker và timestamp lỗi.
2. [ ] Chạy profile dữ liệu: số segment, tỷ lệ finalized, ngôn ngữ, độ dài, duplicate, zero duration, missing speaker và noise.
3. [ ] Ghi rõ timestamp chuẩn: lưu cả thời gian tương đối và `absolute_start_at`/`absolute_end_at` khi nguồn có cung cấp.
4. [ ] Chốt normalized schema cho transcript segment và analysis unit: source segment IDs, revision, text raw/normalized, speaker, thời gian, quality status/reasons, language, preprocessing version.
5. [ ] Viết hoặc bổ sung unit test contract cho các fixture ở bước 1.

**Hoàn thành khi:** có báo cáo data-quality ngắn, fixture không chứa dữ liệu nhạy cảm, và test chứng minh revision/retract/duplicate xử lý đúng.

### P2 — Củng cố database, job lifecycle và adapter nền tảng

**Mục tiêu:** bảo đảm dữ liệu bền vững, retry không tạo bản ghi sai và sẵn sàng mở rộng nền tảng.

1. [ ] Rà migration/schema hiện có so với danh sách bắt buộc: `meetings`, `participants`, `transcript_segments`, `incoming_webhooks`, `outbox_events`, `analysis_runs`, `analysis_units`, `sentiment_predictions`, `meeting_sentiment_windows`, `model_registry`, `annotation_tasks`.
2. [ ] Bổ sung phần còn thiếu: `transcript_revision` ở meeting; `is_current`/invalidation prediction; unique key run `(meeting_id, kind, source_revision, model_version)`; index theo meeting/timestamp/speaker.
3. [ ] Kiểm thử repository: upsert segment không tạo dòng trùng; webhook lặp được dedupe; sửa/retract segment làm kết quả cũ không còn current.
4. [ ] Kiểm thử outbox và worker restart: job có idempotency key, retry hữu hạn, DLQ hoặc trạng thái lỗi có thể quan sát; restart không mất job.
5. [ ] Chuẩn hóa interface adapter: `create_meeting`, `stop_meeting`, `sync_transcript`, `normalize_event` và capability/contract của nền tảng.
6. [ ] Hoàn thiện adapter Google Meet + Vexa; với Zoom/Teams/Jitsi chỉ tạo interface, tài liệu contract và checklist xác minh API—không code integration thật khi chưa có sandbox/API hợp lệ.

**Hoàn thành khi:** migration chạy từ database trống; test idempotency pass; finalization chỉ tạo một final job; Vexa key không xuất hiện ở frontend/log.

### P3 — Quality gate, baseline và model registry

**Mục tiêu:** đảm bảo pipeline không ép dự đoán trên transcript kém chất lượng và mọi output tái lập được.

1. [ ] Version hóa preprocessing: Unicode NFC, whitespace/punctuation nhẹ, giữ dấu tiếng Việt, không sửa raw transcript.
2. [ ] Hoàn thiện quality gate: chỉ nhận finalized/non-retracted; loại hoặc gắn `unknown` cho text quá ngắn, lặp, nhiễu, không phải nội dung họp, không phải tiếng Việt hoặc mixed theo policy.
3. [ ] Hoàn thiện unit builder: chỉ gộp 1–3 segment liền nhau của cùng speaker, giới hạn thời gian/token; không gộp qua speaker.
4. [ ] Lưu `quality_reasons`, `source_segment_ids`, `preprocessing_version`, language và model version để giải thích coverage/evidence.
5. [ ] Duy trì `baseline-rules-v1` như smoke test; nếu có dữ liệu gán nhãn, thêm TF-IDF + Logistic Regression làm baseline so sánh.
6. [ ] Tạo/hoàn thiện `model_registry`: model version, labels, artifact URI/checksum, threshold, activation và rollback target.
7. [ ] Viết test cho phủ định tiếng Việt, câu có dấu, PII redaction trong log/export, code-switch, repeated text và draft/retract.

**Hoàn thành khi:** cùng input + cùng version tạo cùng output; mọi unit đều truy ngược về segment nguồn; dữ liệu bị loại hiện `unknown`/reason, không bị gán `neutral`.

### P4 — API, dashboard và realtime

**Mục tiêu:** dashboard giải thích được kết quả và ổn định khi dữ liệu chưa có hoặc cập nhật muộn.

1. [ ] Kiểm thử và hoàn thiện API: overview, timeline, speakers, units/evidence, analysis runs và feedback.
2. [ ] Áp owner/workspace authorization cho mọi REST, evidence và SSE endpoint; kiểm thử user không có quyền nhận `403`/`404`.
3. [ ] Hoàn thiện trạng thái UI: `waiting`, `processing`, `partial`, `completed`, `failed`, loading/empty/error; failure không làm trang trắng.
4. [ ] Dashboard phải hiện: tỷ lệ 3 nhãn, `unknown`, coverage, số unit bị loại, model/version, trạng thái run, timeline và breakdown theo speaker trong phạm vi meeting.
5. [ ] Evidence phải mở được source transcript/timestamp, label, confidence, probability/quality reason và source revision.
6. [ ] Kiểm thử SSE reconnect/replay cursor: không mất event cuối, không render trùng khi reconnect.
7. [ ] Feedback “Đúng/Sai/Không đủ ngữ cảnh” tạo audit trail/annotation task; không sửa prediction lịch sử.

**Hoàn thành khi:** dashboard dùng một application UUID hợp lệ, hiển thị đúng DB; coverage thấp/unknown được diễn giải rõ; người dùng trái quyền không đọc được transcript/evidence.

### P5 — E2E, triển khai và bằng chứng vận hành

**Mục tiêu:** tạo bằng chứng kỹ thuật đủ cho demo và chương đánh giá hệ thống.

1. [ ] Rà Docker Compose CPU; kiểm tra health check backend, PostgreSQL, Valkey, worker và dashboard. GPU compose là tùy chọn.
2. [ ] Viết runbook từ clean start: cấu hình secrets, tạo meeting, admit bot, sync transcript, final analysis, mở dashboard, xử lý lỗi phổ biến.
3. [ ] Chạy test E2E tối thiểu: meeting → Vexa transcript → sync → PostgreSQL → queue/worker → analysis completed → dashboard evidence.
4. [ ] Chạy test tình huống lỗi: webhook lặp, segment revision/retract, worker restart, queue retry, dashboard reconnect và transcript `total=0`.
5. [ ] Thu thập log/ảnh chụp có timestamp: health, danh sách service, API response đã che PII/secret, dashboard, kết quả test; lưu vào thư mục evidence không commit secret.
6. [ ] Đo các chỉ số chỉ từ log thật: thời gian sync/final analysis, P95 inference nếu đủ mẫu, tỷ lệ job fail/retry, coverage/unknown. Ghi rõ cỡ mẫu và môi trường chạy.
7. [ ] Viết monitoring/runbook: queue depth/lag, analysis failure, worker readiness, API 5xx, coverage giảm bất thường, cách retry/rollback.

**Hoàn thành khi:** demo từ clean start lặp lại được; worker restart không làm mất dữ liệu; mọi số liệu trong báo cáo truy ra được log/protocol.

### P6 — Thực nghiệm PhoBERT (chỉ làm khi có dữ liệu và thời gian)

**Không là điều kiện để hoàn thành MVP kiến trúc.** Không bắt đầu fine-tune nếu chưa có consent, guideline và ground truth.

1. [ ] Soạn annotation guideline: polarity, phủ định, sarcasm, code-switching, `unclear/insufficient-context` và ví dụ.
2. [ ] Thu thập 1.000–2.000 analysis unit có consent/ẩn danh; hai annotator độc lập; adjudication bất đồng; đo agreement.
3. [ ] Split train/validation/test theo **meeting**, version hóa dataset manifest và seed.
4. [ ] So sánh trên cùng holdout: baseline rules, TF-IDF + Logistic Regression, checkpoint PhoBERT phù hợp.
5. [ ] Fine-tune PhoBERT chỉ nếu có lý do; lưu config, seed, artifact checksum, confusion matrix, macro-F1, F1 từng lớp, calibration, coverage và P95 latency.
6. [ ] Chọn threshold `unknown` trên validation; shadow run/canary trước khi activate; chuẩn bị rollback model version.

**Hoàn thành khi:** có model card + evaluation report; chỉ promote nếu đạt gate chất lượng/latency đã chốt. Nếu không đạt, báo cáo trung thực baseline và giới hạn.

### P7 — Hoàn thiện luận văn và hồ sơ bàn giao

1. [ ] Cập nhật sơ đồ: kiến trúc tổng quan, ERD, sequence diagram ingestion/final analysis và deployment topology.
2. [ ] Đồng bộ chương báo cáo với implementation thực tế: stack, API, schema, quality gate, dashboard và test.
3. [ ] Viết chương đánh giá theo protocol: môi trường, dữ liệu, kịch bản, chỉ số, kết quả, lỗi/giới hạn; không điền số liệu minh họa như kết quả thật.
4. [ ] Rà soát terminology: “sentiment của transcript”, không ghi “chẩn đoán/evaluate emotion của người”. Ghi rõ baseline rules không phải PhoBERT.
5. [ ] Thêm phụ lục: API contract, test matrix, ảnh dashboard, runbook, model card (nếu có) và checklist bảo mật/consent.
6. [ ] Biên dịch PDF từ đầu, kiểm tra mục lục/danh mục hình/bảng, references, hình tràn lề, link và chính tả.
7. [ ] Chạy rehearsal bảo vệ 10–15 phút: bài toán → kiến trúc → demo/E2E → đánh giá → giới hạn → hướng phát triển.

**Hoàn thành khi:** PDF biên dịch sạch, mọi claim kỹ thuật có bằng chứng, demo/runbook lặp lại được và phụ lục khớp mã nguồn.

## 5. Checklist chạy mỗi ngày

1. [ ] Chọn **một** task chưa hoàn thành ở phase hiện tại; ghi branch/commit hoặc file liên quan.
2. [ ] Thực hiện thay đổi nhỏ nhất có thể, sau đó chạy test đúng phạm vi.
3. [ ] Cập nhật task với kết quả, lệnh test, log/ảnh bằng chứng và blocker (nếu có).
4. [ ] Chỉ chuyển sang task phụ thuộc sau khi checkpoint gần nhất pass.
5. [ ] Cuối ngày: cập nhật bảng tiến độ, backup tài liệu/bằng chứng và ghi 3 việc ưu tiên ngày sau.

## 6. Ma trận Definition of Done cuối cùng

| Hạng mục | Điều kiện phải đạt |
|---|---|
| Correctness | Prediction truy ngược đến segment, revision, normalized text, preprocessing và model version. |
| Idempotency | Retry/restart/webhook lặp không tạo run, prediction hay aggregate trùng. |
| Quality | Draft/retract/noise/short/non-Vietnamese theo đúng policy; `unknown` độc lập với neutral. |
| Dashboard | KPI, timeline, evidence/timestamp, coverage và state xử lý khớp database. |
| Realtime | Final segment cập nhật theo debounce/SLA mục tiêu; reconnect không mất hoặc lặp event. |
| Security/privacy | Không lộ secret/raw transcript/PII trong client bundle và log; API có authorization. |
| Operations | Compose/health check/runbook, retry, worker restart và rollback được kiểm thử. |
| Thesis evidence | Mọi chỉ số/claim có protocol, môi trường, cỡ mẫu và log/ảnh chụp đối chiếu. |

## 7. Thứ tự ưu tiên nếu thời gian hạn chế

1. P0 → P2: chốt scope, contract, migration/idempotency.
2. P3 → P5: quality gate, dashboard/evidence, E2E và runbook.
3. P7: cập nhật báo cáo đúng với phần đã chạy.
4. P6 chỉ thực hiện khi đã có dữ liệu gán nhãn hợp lệ; nếu không, ghi là hướng phát triển thay vì tuyên bố đã fine-tune.

