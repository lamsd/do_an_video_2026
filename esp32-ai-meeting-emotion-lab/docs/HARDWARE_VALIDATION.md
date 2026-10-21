# Runbook xác nhận phần cứng trước khi flash

Hệ thống này hỗ trợ đúng bốn board, không có auto-discovery thay thế kiểm tra identity.

## Chuẩn bị bench

1. Dán nhãn vật lý `ESP32-01` đến `ESP32-04`; ghi serial/MAC/port vào study log.
2. Chạy simulator trước và xác nhận dashboard có bốn `device_id` `esp32-01`…`esp32-04`, mỗi cái có MQTT client riêng.
3. Thay toàn bộ mật khẩu `.env.example`; không cho board dùng password của `backend`.
4. Đặt broker/board ở Wi‑Fi hoặc VLAN cô lập. Không expose port 1883 ra Internet; dùng TLS trước khi dùng ngoài mạng local.
5. Kiểm tra broker host đã reachable từ từng board và firmware size phù hợp partition board.

## Flash lần lượt

1. Sao chép `firmware/include/secrets.example.h` sang `secrets.h`, điền SSID/password Wi‑Fi, MQTT host và bốn password khác nhau.
2. Kết nối duy nhất ESP32-01, build/flash environment `esp32-01`, kiểm tra nó đăng ký là `empathy` + `esp32-01`.
3. Lặp lại theo cặp cố định: `esp32-02/critical`, `esp32-03/optimistic`, `esp32-04/moderator`.
4. Không flash environment của board này sang board được dán nhãn khác. Backend sẽ reject mismatch nhưng không thể tự sửa board đã nạp sai.
5. Cấp nguồn đồng thời bốn board và chờ heartbeat; chỉ khi đủ bốn online mới mở nút bắt đầu.

## Nghiệm thu bắt buộc

1. Start một phiên một vòng. Phải có chính xác năm turn theo `moderator, empathy, critical, optimistic, moderator` từ bốn device cố định.
2. Replay `turn/published` qua MQTT; DB không được tăng thêm turn.
3. Power-cycle một board. LWT/TTL phải làm chỉ board đó `disconnected`; backend không được start phiên mới.
4. Pause trong lúc có lượt; response đến muộn không được tạo record. Resume phải cấp token mới đúng lượt đang chờ.
5. Stop rồi start phiên mới; tất cả board nhận control `resume` và chỉ board được cấp mới publish.
6. Khi bật OpenAI TTS, kiểm tra mỗi turn có WAV, RMS, pitch/MFCC/Mel (hoặc metadata nói rõ `librosa` thiếu) và playback đúng transcript.

## Không được tuyên bố đã kiểm chứng

Code repository không flash phần cứng, đo sóng Wi‑Fi, áp dụng TLS certificate, kiểm tra secret rotation, hay tạo bốn participant Jitsi media thật. Những việc này cần board, network, account/credentials và consent của triển khai cụ thể.
