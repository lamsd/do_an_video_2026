# Kiến trúc, trust boundary và phases

## Luồng dữ liệu

```text
React dashboard ──HTTP──> FastAPI / TurnCoordinator ──MQTT──> Mosquitto
                                  │                       ├── esp32-01 / empathy
                                  │                       ├── esp32-02 / critical
                                  │                       ├── esp32-03 / optimistic
                                  │                       └── esp32-04 / moderator
                                  ├── PostgreSQL
                                  ├── OpenAI Responses + TTS (backend-only)
                                  ├── WAV + RMS/Pitch/MFCC/Mel extraction
                                  └── MeetingAdapter interface (Jitsi media adapter sau này)
```

Board không có microphone, speaker, API key, model GPT, database hay quyền tự tăng lượt. MQTT device credentials chỉ cho phép namespace của chính device và đọc context chung; tài khoản backend là coordinator duy nhất.

## Thuật toán điều phối

1. Bốn board đăng ký đúng cặp `agent_id`/`device_id` và gửi heartbeat retained/LWT.
2. Dashboard chỉ gọi backend tạo phiên khi cả bốn trạng thái không phải `disconnected`.
3. Coordinator sinh `turn_token`, `turn_id` và `sequence_number`, lưu token hoạt động, rồi publish `turn/grant` chỉ cho agent đầu danh sách.
4. Board được cấp relay `generation/request`; backend mới gọi GPT và gửi đúng response về topic của board đó.
5. Board echo nguyên văn response với token/turn id/sequence. Coordinator chỉ lưu turn nếu identity, token, turn id, thứ tự và nội dung đã cấp đều khớp.
6. Backend sinh WAV/phân tích sau khi relay được chấp nhận, ghi PostgreSQL, publish context mới và chỉ khi đó cấp lượt tiếp theo.
7. Đủ số vòng thì session `completed`; pause/stop xóa capability token đang hoạt động nên response đến muộn bị từ chối.

Một vòng dùng `moderator → empathy → critical → optimistic → moderator`. Đây là năm lượt vai trò có chủ đích, không phải năm thiết bị.

## Tính riêng tư và dữ liệu nghiên cứu

- Nội dung transcript, file WAV và metadata chỉ nên lưu trong môi trường đã có consent; đặt retention/deletion policy trước nghiên cứu thật.
- MQTT phải ở VLAN/broker private, TLS/mTLS hoặc secret rotation trước deployment. Mật khẩu ví dụ chỉ dùng local development.
- `emotion_prediction=unavailable` là kết quả đúng khi thiếu checkpoint độc lập. Không có code suy luận trầm cảm.
- TTS là audio tổng hợp. Nó không thể thay thế mẫu giọng người để đánh giá sức khỏe tâm thần hoặc xác nhận cảm xúc người nói.

## Trạng thái phases

| Phase | Mục tiêu | Trạng thái mã nguồn |
| --- | --- | --- |
| 1 | Bốn MQTT clients mô phỏng board | Có simulator độc lập, LWT, ACL, heartbeat, token test |
| 2 | GPT multi-agent/routing | Có backend-only generator và prompt tiếng Việt; offline template an toàn |
| 3 | Flash 4 ESP32 | Có target ESP-IDF chính và source PlatformIO tương thích; chưa flash hay compile tại workspace này |
| 4 | TTS/WAV/feature extraction | Có pipeline, persistence contract, UI playback; cần OpenAI key để sinh TTS thật |
| 5 | 4 Jitsi participants | Có contract/test double; adapter media Jitsi thật chưa triển khai |
| 6 | Tracking/evaluation/dashboard | Có PostgreSQL model, API, React dashboard và test nền tảng; cần dataset/checkpoint/evaluation study thật |

Các giới hạn không phải lỗi bị che giấu: chỉ thử nghiệm phase 1+2 cục bộ với broker/Compose, board và Jitsi phải được nghiệm thu bằng hạ tầng thật.
