# Tasks hoàn thiện khóa luận

**Đề tài:** Hệ thống phân tích sắc thái cảm xúc từ transcript tiếng Việt trong họp trực tuyến
**Mục tiêu:** Hoàn thiện bằng chứng kiểm chứng, kết quả thực nghiệm và báo cáo theo đúng phạm vi của một hệ thống phân tích transcript có khả năng truy vết.

> Quy ước: chỉ đánh dấu hoàn thành khi có artefact kiểm tra được (log, ảnh đã lược bỏ dữ liệu nhạy cảm, bảng số liệu hoặc phần luận văn đã cập nhật). Không suy diễn độ chính xác mô hình từ coverage hay snapshot Dashboard.

## P0 — Bắt buộc trước khi chốt thực nghiệm

- [ ] **Chốt phạm vi và tuyên bố nghiên cứu**
  - Xác định Jitsi Meet là nền tảng thực nghiệm chính.
  - Nêu Google Meet, Zoom và Microsoft Teams chỉ là hướng mở rộng, chưa được kiểm chứng runtime.
  - Xác định baseline runtime là `baseline-rules-v3`; không tuyên bố đây là PhoBERT hoặc mô hình sentiment đã được đánh giá.
  - **Hoàn thành khi:** Chương 1, 8 và 10 dùng cùng một phạm vi và cách diễn giải.

- [ ] **Khắc phục trạng thái không nhất quán trên Dashboard**
  - Tái hiện và tìm nguyên nhân trường hợp một run hiện `succeeded` nhưng vùng khác hiện `queued` hoặc `0/0` unit.
  - Kiểm tra dữ liệu API, persistence, cache/SSE và cách Dashboard refresh run đang chọn.
  - Thêm hoặc cập nhật test để tránh tái diễn.
  - **Hoàn thành khi:** Cùng một run có trạng thái, revision và số unit nhất quán giữa API, backend và Dashboard.

- [ ] **Chạy kiểm chứng End-to-End trên Jitsi Meet**
  - Tạo phòng test, nhận consent của người tham gia và cho Vexa bot tham gia.
  - Xác nhận final transcript đi qua backend, queue, worker và xuất hiện ở Dashboard.
  - Kiểm tra quality gate, analysis unit, `unknown`, coverage, timeline và evidence theo run.
  - **Hoàn thành khi:** Một run hoàn chỉnh được xác nhận theo checklist Jitsi E2E.

- [ ] **Tạo evidence bundle E2 cho runtime hiện tại**
  - Chạy `dashboard-acceptance.sh` cho Application Meeting UUID cục bộ.
  - Lưu lệnh chạy, timestamp, commit hoặc image digest, exit code, log/API export đã redaction và ảnh Dashboard.
  - Không đưa transcript thật, UUID thật, tên người nói, token hoặc secret vào Git hay luận văn.
  - **Hoàn thành khi:** Có bundle tái lập được cho `baseline-rules-v3`, không dùng bundle lịch sử `baseline-rules-v2` để thay thế.

## P1 — Thực nghiệm và phân tích kết quả

- [ ] **Chuẩn bị test plan pilot**
  - Soạn 10–20 lượt lời hoặc scene gồm positive, neutral, negative, tiếng Anh và Việt–Anh trộn.
  - Ghi nhãn mục tiêu trước khi chạy và không chỉnh nhãn sau khi xem dự đoán.
  - Quy định rõ đơn vị đánh giá: segment hay analysis unit; quy tắc xử lý `unknown` và unit bị reject.
  - **Hoàn thành khi:** Có test plan, nhãn tham chiếu và phiên bản kịch bản được khóa.

- [ ] **Thực hiện pilot hai người dùng và một bot**
  - Thực hiện theo test plan; ghi thời điểm bot join, thời điểm transcript final và ID run nội bộ.
  - Lưu số segment, số segment accepted/rejected, analysis unit, predicted unit và `unknown`.
  - **Hoàn thành khi:** Có dữ liệu pilot đã ẩn danh cùng evidence bundle tương ứng.

- [ ] **Tổng hợp chỉ số vận hành**
  - Tính `accepted/final/total`, prediction coverage, effective coverage, tỷ lệ `unknown` và thời gian xử lý.
  - Phân biệt rõ các chỉ số vận hành với accuracy/F1 của sentiment.
  - **Hoàn thành khi:** Có bảng số liệu, biểu đồ timeline/coverage và chú thích điều kiện chạy.

- [ ] **Đánh giá sentiment ở quy mô phù hợp**
  - Đối chiếu prediction với nhãn tham chiếu đã khóa.
  - Báo cáo confusion matrix; nếu kích thước mẫu đủ, báo cáo Macro-F1, precision và recall theo lớp.
  - Nêu kích thước mẫu, phân bố nhãn, cách gán nhãn và giới hạn suy rộng.
  - **Hoàn thành khi:** Có bảng đánh giá không nhầm lẫn giữa coverage và chất lượng dự đoán.

- [ ] **Phân tích lỗi**
  - Chọn 5–10 trường hợp đại diện: rejected unit, code-switching, lỗi STT, thiếu ngữ cảnh, `unknown` và dự đoán không phù hợp.
  - Phân loại nguyên nhân thuộc STT, quality gate, unit builder, language routing hay classifier baseline.
  - **Hoàn thành khi:** Có bảng error analysis đã redaction và đề xuất cải tiến cụ thể.

## P2 — Củng cố đánh giá hệ thống

- [ ] **Đánh giá STT khi có transcript tham chiếu**
  - Chuẩn bị transcript gõ tay đã kiểm tra và được phép dùng.
  - Tính WER/CER, nêu rõ số lượt lời, ngôn ngữ và điều kiện âm thanh.
  - **Hoàn thành khi:** Có báo cáo WER/CER; nếu không có dữ liệu tham chiếu, ghi rõ chỉ số này chưa đo.

- [ ] **Đo hiệu năng pipeline**
  - Ghi thời gian từ ingest/final transcript đến prediction và Dashboard.
  - Thực hiện nhiều lượt chạy; báo cáo P50/P95 khi số lượt phù hợp.
  - Ghi cấu hình máy, image/runtime và điều kiện tải.
  - **Hoàn thành khi:** Có bảng latency và không gọi batch duration là latency E2E.

- [ ] **Kiểm thử lỗi vận hành**
  - Kiểm tra worker restart, Valkey unavailable, webhook bị trùng/replay và SSE reconnect.
  - Ghi expected result, kết quả thực tế, recovery và bằng chứng pass/fail.
  - **Hoàn thành khi:** Có bảng resilience/failure test.

## P3 — Hoàn thiện luận văn và bảo vệ

- [ ] **Cập nhật Chương 8 — Thực nghiệm**
  - Thay snapshot đơn lẻ bằng bảng evidence, bảng metric, biểu đồ và error analysis.
  - Phân tách rõ E0/E1/E2; chỉ gọi PASS khi có evidence E2.
  - **Hoàn thành khi:** Mọi kết luận đều truy ngược được đến artefact kiểm chứng.

- [ ] **Cập nhật Chương 10 — Kết luận**
  - Kết luận về khả năng tích hợp, truy vết và kiểm chứng đúng bằng chứng hiện có.
  - Không khẳng định chất lượng PhoBERT, chất lượng sentiment, WER, SLA hay đa nền tảng nếu chưa đo.
  - **Hoàn thành khi:** Kết luận trả lời trực tiếp các câu hỏi nghiên cứu.

- [ ] **Rà soát chất lượng báo cáo**
  - Chuẩn hóa số bảng/hình, caption, thuật ngữ, trích dẫn và tham chiếu chéo.
  - Kiểm tra PDF không lỗi citation/reference và không lộ dữ liệu nhạy cảm.
  - **Hoàn thành khi:** Có PDF final đã được rà soát.

- [ ] **Chuẩn bị bảo vệ**
  - Tạo slide: vấn đề → phạm vi → kiến trúc → pipeline → pilot/evidence → kết quả → giới hạn → đóng góp.
  - Chuẩn bị demo ngắn với dữ liệu không nhạy cảm và phương án dự phòng bằng ảnh/video đã redaction.
  - **Hoàn thành khi:** Trình bày thử được trong 5–7 phút và demo hoạt động hoặc có backup.

## Tiêu chí sẵn sàng nộp

- [ ] Evidence E2 cho Jitsi E2E runtime `baseline-rules-v3`.
- [ ] Pilot có test plan, nhãn tham chiếu và kết quả đã tổng hợp.
- [ ] Ít nhất một bảng đánh giá vận hành và một bảng phân tích lỗi.
- [ ] Chương thực nghiệm, kết luận và abstract khớp với bằng chứng.
- [ ] PDF cuối không lỗi tham chiếu và không chứa dữ liệu nhạy cảm.
