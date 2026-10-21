# Trạng thái triển khai trung thực

## Có trong source tree

- Docker Compose: Mosquitto ACL/password bootstrap, PostgreSQL, FastAPI, simulator bốn client và React dashboard.
- Python backend: identity cố định, state machine, envelope MQTT, coordinator tokenized, REST API, GPT/TTS adapter, WAV/feature extraction, PostgreSQL models.
- Firmware PlatformIO: Wi‑Fi/MQTT/LWT, heartbeat, grant/request/response/relay/control; không có microphone/speaker/API key.
- Contract mô hình cảm xúc và Jitsi, cùng `InMemoryMeetingAdapter` để test không cần server Jitsi.
- Unit tests cho thứ tự turn, state transitions và meeting contract.

## Cần môi trường/authority bổ sung

- Compile và flash firmware với toolchain/board thật.
- Khởi động Docker engine và chạy full end-to-end broker + Compose.
- Cung cấp OpenAI key cho GPT/TTS thật; key vẫn chỉ đi vào backend environment.
- Huấn luyện, đánh giá, version/checksum và load một checkpoint acoustic-emotion riêng. Chỉ sau đó mới thay `unavailable` bằng output model được kiểm định.
- Viết adapter media Jitsi cụ thể (lib-jitsi-meet/bot transport), quản lý room credentials, publish PCM/WAV cho bốn account và xin consent/retention approval.

## Không làm

- Không suy luận depression/diagnosis/risk từ WAV, text sentiment hay cảm xúc ước lượng.
- Không giả lập thành công Jitsi participant hoặc ESP32 physical flash.
- Không đưa API key vào `firmware`, `frontend`, database record hay MQTT message.
