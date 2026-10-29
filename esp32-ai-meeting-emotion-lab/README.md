# ESP32 Distributed AI Meeting & Emotion Lab

Thư mục này là mô phỏng có thể chạy trong workspace khóa luận hiện hữu; **không phải Git repository mới**. Hệ thống mô hình hóa đúng bốn ESP32 vật lý không có microphone hay loa. Các board chỉ xác thực, giữ trạng thái, nhận/cấp lượt và relay bản tin MQTT. GPT, TTS, phân tích âm học, cơ sở dữ liệu và giao diện Jitsi chạy ở Ubuntu backend.

Mọi tác nhân, giao diện và prompt sinh nội dung đều dùng tiếng Việt.

## Bốn định danh bất biến

| Board vật lý | Tác nhân AI | `device_id` | MQTT user | Voice TTS | Jitsi participant |
| --- | --- | --- | --- | --- | --- |
| ESP32-01 | Thấu cảm | `esp32-01` | `empathy` | `nova` | `ai-empathy-01` |
| ESP32-02 | Phản biện | `esp32-02` | `critical` | `onyx` | `ai-critical-02` |
| ESP32-03 | Lạc quan | `esp32-03` | `optimistic` | `coral` | `ai-optimistic-03` |
| ESP32-04 | Điều phối | `esp32-04` | `moderator` | `sage` | `ai-moderator-04` |

Không được dùng OpenAI key trong firmware, dashboard hoặc MQTT payload. Mỗi board có mật khẩu MQTT, client ID, LWT, heartbeat, topic riêng và trạng thái riêng. Backend từ chối mọi cặp `agent_id`/`device_id` không đúng bảng trên.

## Chạy Phase 1: mô phỏng MQTT bốn thiết bị

```bash
cd /home/lamsd/Documents/Buildkhoaluan/esp32-ai-meeting-emotion-lab
cp .env.example .env
docker compose up --build
```

Docker Compose truyền `POSTGRES_PASSWORD` trực tiếp cho backend và tạo PostgreSQL URL an toàn. Chỉ đặt `DATABASE_URL` khi chạy backend ngoài Docker; đây là credential DB, không phải MQTT password.

Mở <http://localhost:8080>. Khi bốn thẻ thiết bị có trạng thái trực tuyến, nhập đề tài và bắt đầu phiên. Nếu không đặt `OPENAI_API_KEY`, backend tạo văn bản mẫu ngoài tuyến và tone WAV được dán nhãn rõ ràng để kiểm thử đường đi MQTT; tone này không phải tiếng nói có ngữ nghĩa. Nếu đặt khóa OpenAI ở backend, mỗi lượt tạo tiếng Việt và WAV bằng OpenAI TTS. Mặc định là `tts-1` để thử nghiệm nhanh, độ trễ thấp; có thể đặt `OPENAI_TTS_MODEL=gpt-4o-mini-tts` nếu cần điều khiển phong cách giọng chi tiết hơn. Mỗi WAV được đo RMS/peak sau khi tạo; WAV im lặng hoặc TTS lỗi được thay bằng tone kiểm thử và ghi rõ nguồn trong dashboard.

Thứ tự một vòng là hữu hạn và được điều phối tập trung:

```text
AI-Moderator-04 (mở đầu) → AI-Empathy-01 → AI-Critical-02 →
AI-Optimistic-03 → AI-Moderator-04 (tổng kết)
```

Đây vẫn là **bốn thiết bị**: Moderator có hai lượt khác vai trò trong cùng một vòng. Có thể tạm dừng, tiếp tục hoặc dừng phiên từ dashboard.

## Giao thức và chống lỗi điều phối

Mọi MQTT envelope dùng `schema_version`, `message_id`, `timestamp`, `device_id`, `agent_id`, `session_id`, `event_type`, `turn_id`, `sequence_number` (khi áp dụng) và `payload`. Các topic chính là:

| Topic | Ghi bởi | Đọc bởi | Mục đích |
| --- | --- | --- | --- |
| `lab/device/<agent>/register` | board | backend | đăng ký định danh cố định |
| `lab/device/<agent>/heartbeat` | board/LWT | backend | trạng thái và liveness retained |
| `lab/device/<agent>/turn/grant` | backend | đúng board đó | cấp token cho đúng một lượt |
| `lab/device/<agent>/generation/request` | board được cấp | backend | yêu cầu GPT ở Ubuntu |
| `lab/device/<agent>/generation/response` | backend | đúng board đó | trả văn bản để relay |
| `lab/device/<agent>/turn/published` | board được cấp | backend | xác nhận văn bản đã cấp |
| `lab/device/<agent>/control` | backend | đúng board đó | pause/resume/stop |
| `lab/session/<id>/context` | backend | tất cả board | đề tài + transcript chung retained |

`TurnCoordinator` là nguồn chân lý duy nhất: nó kiểm tra board online, lượt mong đợi, UUID token, nội dung đã cấp và giới hạn số vòng trước khi ghi DB hay cấp lượt kế. Bản tin trùng, ngoài thứ tự hoặc vòng lặp không được tiến trạng thái.

Trạng thái board là: `BOOTING → WIFI_CONNECTING → MQTT_CONNECTING → REGISTERING → READY → LISTENING → THINKING → SPEAKING → READY`, cùng các trạng thái `PAUSED`, `STOPPED`, `DISCONNECTED`, `ERROR`.

## Firmware thật: sau khi mô phỏng đạt yêu cầu

Target ESP-IDF chính ở [`firmware/esp-idf/`](firmware/esp-idf/) có project CMake, Kconfig và defaults template cho bốn board. Sao chép đúng `config/esp32-0N.defaults.example` thành file `.defaults` bị git-ignore rồi build với `idf.py`; xem [hướng dẫn ESP-IDF](firmware/esp-idf/README.md). Bản Arduino/PlatformIO tương thích vẫn có ở [`firmware/`](firmware/) để bench nhanh. Sao chép `include/secrets.example.h` thành `include/secrets.h`, điền Wi‑Fi, IP/DNS broker và mật khẩu riêng, rồi nạp **từng board đúng environment**:

```bash
cd firmware
pio run -e esp32-01 -t upload
pio run -e esp32-02 -t upload
pio run -e esp32-03 -t upload
pio run -e esp32-04 -t upload
```

Chỉ flash sau [hardware validation](docs/HARDWARE_VALIDATION.md). Repository không thể tự chứng minh đã flash board, kết nối Wi‑Fi thực hay đã tham gia Jitsi thật.

## Âm thanh, cảm xúc và ranh giới nghiên cứu

Sau lượt đã được backend chấp nhận, `data/media/<session>/<turn>.wav` được tạo và metadata RMS, pitch, MFCC, Mel-spectrogram, giọng, transcript, token được ghi vào PostgreSQL. Khi `librosa` không có, metadata tối thiểu được ghi kèm chỉ dẫn cài đặt; không có dữ liệu bị bịa.

Contract `backend/app/emotion/` chỉ cho phép checkpoint cảm xúc đã huấn luyện và đánh giá độc lập. Mặc định API trả `unavailable`. Không diễn giải sentiment văn bản, phong cách voice, tín hiệu âm học hay âm thanh tổng hợp thành trầm cảm, chẩn đoán hoặc rủi ro sức khỏe tâm thần.

## Jitsi: interface trước, bot thật sau

[`backend/app/meeting/adapter.py`](backend/app/meeting/adapter.py) có interface kiểm thử cho kết nối, join/leave room, danh sách participant, subscribe/publish audio, trạng thái kết nối và đóng transport; mỗi participant hiển thị rõ là `AI Bot · ...`. `InMemoryMeetingAdapter` chỉ là test double.

Chưa có adapter Jitsi media chạy thật trong repository. Bốn bot Jitsi độc lập cần một transport media có thể publish track WAV/PCM, thông tin đăng nhập và quy trình consent/retention. Jitsi IFrame API đơn thuần không cung cấp raw audio track để thay thế adapter này.

## Kiểm thử và vận hành

```bash
uv venv
uv pip install -e '.[dev]'
uv run pytest -q
uv run ruff check backend simulator tests
uv run mypy backend/app simulator
docker compose --env-file .env.example config
```

Xem [kiến trúc và trạng thái phase](docs/ARCHITECTURE.md), [runbook thiết bị](docs/HARDWARE_VALIDATION.md), và [giới hạn/việc còn lại](docs/IMPLEMENTATION_STATUS.md). Các scripts hỗ trợ ở [`scripts/`](scripts/).
