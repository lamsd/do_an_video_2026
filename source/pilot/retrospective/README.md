# Pilot duy nhất: xem lại retrospective một cuộc họp

## Mục tiêu và phạm vi

Pilot này chỉ trả lời một nhu cầu: sau một Google Meet đã kết thúc, người vận hành xem lại diễn biến trao đổi qua timeline sentiment, transcript và evidence theo từng analysis unit. Nó không đánh giá hiệu suất, cảm xúc bền vững, sức khỏe tâm thần hay ra quyết định về người tham gia.

Chỉ sử dụng pipeline hiện có: `Google Meet -> Vexa -> backend -> worker -> Dashboard`. Không mở rộng sang Zoom, Teams, Kubernetes, ghi âm ngoài Vexa hay tự động gửi kết quả cho người khác.

## Điều kiện trước pilot

1. Có một người vận hành và người tham gia đồng ý rõ ràng trước khi bot vào họp.
2. Nội dung thử nghiệm ngắn, không nhạy cảm; không dùng làm đánh giá nhân sự/học tập.
3. Dashboard chỉ mở tại `127.0.0.1`; người vận hành không chia sẻ UUID, transcript, screenshot hoặc API key ra ngoài phạm vi đã đồng ý.
4. `source/scripts/runtime-status.sh`, `source/scripts/verify.sh` và smoke evidence đã PASS.
5. Classifier đã được ghi đúng `MODEL_VERSION`; nếu dùng TF-IDF + Logistic Regression, artifact hash và file `evaluation.json` đã được duyệt.

## Kịch bản vận hành

1. Lưu consent ngoài repository. Mẫu tối thiểu: mục đích retrospective; loại dữ liệu transcript; thời gian lưu; người được xem; quyền từ chối/xóa.
2. Tạo Google Meet thử nghiệm, mời bot bằng `POST /v1/meetings`, và chỉ admit bot sau khi xác nhận consent.
3. Khi meeting kết thúc, gọi `POST /v1/meetings/<uuid>/sync`, sau đó `POST /v1/meetings/<uuid>/analysis?kind=final` nếu webhook chưa tự tạo final run.
4. Mở Dashboard tại cổng local đã cấu hình, để trống UUID để chọn meeting gần nhất hoặc nhập application UUID. Kiểm tra model version, coverage, timeline, speaker và evidence trước khi diễn giải.
5. Người vận hành làm bốn tác vụ: xác định một thay đổi timeline; mở evidence nguồn; nhận biết unit `unknown`/bị từ chối; xác nhận đây không là nhận định về con người.
6. Ghi kết quả pilot đã redaction vào evidence bundle: số người, nhiệm vụ hoàn thành, thời gian, phản hồi, issue. Xóa hoặc áp dụng retention đúng như consent sau pilot.

## Tiêu chí pass

- Bot/transcript được xử lý có consent; dashboard hiển thị đúng application UUID.
- Mỗi KPI/timeline truy ngược được đến evidence unit và transcript segment.
- Dashboard hiển thị model version và coverage; người vận hành nêu đúng giới hạn sử dụng.
- Không có raw transcript, danh tính, API key hay consent form trong Git/evidence bundle.

Pilot chứng minh khả năng vận hành của một use case hẹp; không là benchmark ASR, chất lượng sentiment tổng quát hay user study có tính khái quát.
