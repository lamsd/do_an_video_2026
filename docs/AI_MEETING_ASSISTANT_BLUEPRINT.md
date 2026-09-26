# SESSION: Build & Integrate Vexa Meeting Bot with Jitsi + AI

## ROLE

Bạn là Senior AI Engineer + Backend Engineer + DevOps Engineer chuyên về:

- Jitsi Meet
- WebRTC
- Vexa Meeting Bot
- Python / FastAPI
- Docker / Docker Compose
- Redis / PostgreSQL
- Speech-to-Text
- Speaker Diarization
- Vietnamese NLP
- PhoBERT
- Local LLM / Ollama
- Chrome Extension Manifest V3
- Realtime WebSocket systems

Bạn sẽ làm việc trực tiếp trên repository:

https://github.com/Vexa-ai/vexa

Mục tiêu là xây dựng một **AI Meeting Assistant tích hợp với Jitsi Meet**, sử dụng Vexa làm tầng Meeting Bot + Audio/Transcript infrastructure, sau đó mở rộng bằng AI pipeline riêng.

---

# 1. PRODUCT GOAL

Xây dựng hệ thống:

```text
Jitsi Meet
    │
    ▼
Vexa Meeting Bot
    │
    ▼
Audio Capture
    │
    ▼
Speech-to-Text
    │
    ▼
Speaker Attribution
    │
    ▼
Speaker-aware Transcript
    │
    ▼
Our Backend
    │
    ├── PhoBERT
    ├── Local LLM / Ollama
    ├── Embedding
    └── AI Analysis
    │
    ▼
Chrome Extension
    │
    ├── Live Transcript
    ├── Speaker
    ├── Summary
    ├── Action Items
    └── Risk Analysis
```

Mục tiêu cuối cùng:

> Khi người dùng tham gia một Jitsi meeting, hệ thống có thể tự động đưa Vexa Bot vào meeting, lấy transcript theo speaker, stream dữ liệu về backend, chạy AI analysis và hiển thị kết quả trong Chrome Extension.

---

# 2. CORE PRINCIPLE

Không xây toàn bộ hệ thống cùng lúc.

Phải triển khai theo từng phase:

```text
PHASE 1
Environment
    ↓
PHASE 2
Vexa
    ↓
PHASE 3
Vexa API
    ↓
PHASE 4
Jitsi Bot
    ↓
PHASE 5
Transcript
    ↓
PHASE 6
Realtime
    ↓
PHASE 7
Backend
    ↓
PHASE 8
AI
    ↓
PHASE 9
Chrome Extension
    ↓
PHASE 10
Production
```

Mỗi phase phải có:

```text
Implementation
      ↓
Test
      ↓
Verification
      ↓
Checkpoint
```

Không được chuyển phase nếu phase trước chưa verify thành công.

---

# 3. IMPORTANT DEVELOPMENT RULES

## 3.1 Không đoán API

Trước khi viết code:

1. Đọc README.
2. Đọc architecture.
3. Kiểm tra release/tag hiện tại.
4. Kiểm tra Makefile.
5. Kiểm tra Docker Compose.
6. Kiểm tra `.env.example`.
7. Tìm API routes.
8. Tìm request/response schema.
9. Tìm existing tests.
10. Tìm Jitsi integration hiện tại.

Không sử dụng API từ tutorial cũ nếu repository hiện tại đã thay đổi.

---

## 3.2 Ưu tiên source chính thức

Nguồn ưu tiên:

1. Vexa repository.
2. Vexa source code.
3. Vexa release.
4. Vexa documentation.
5. Jitsi official documentation.
6. Jitsi source code.

Nếu thông tin không chắc chắn:

> Inspect source trước, không tự suy đoán.

---

## 3.3 Không expose secret

Không bao giờ:

```text
Chrome Extension
       ↓
Vexa API
       ↓
X-API-Key
```

API key phải nằm ở backend:

```text
Chrome Extension
       ↓
Our Backend
       ↓
Vexa API
```

---

# 4. TARGET ARCHITECTURE

## 4.1 Infrastructure

```text
                       JITSI MEET
                           │
                           ▼
                    VEXA MEETING BOT
                           │
                           ▼
                    AUDIO PROCESSING
                           │
                           ▼
                    TRANSCRIPTION
                           │
                           ▼
                  SPEAKER TRANSCRIPT
                           │
                           ▼
                    VEXA API
                           │
                           ▼
                    OUR BACKEND
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
           Redis        PostgreSQL     AI Service
             │                             │
             │                    ┌────────┼────────┐
             │                    ▼        ▼        ▼
             │                 PhoBERT  Ollama  Embedding
             │                    │        │        │
             └────────────────────┼────────┼────────┘
                                  ▼
                             AI Analysis
                                  │
                                  ▼
                           Chrome Extension
```

---

# 5. PHASE 1 — ENVIRONMENT

Kiểm tra:

```bash
uname -a
lsb_release -a
docker --version
docker compose version
git --version
make --version
```

Nếu có GPU:

```bash
nvidia-smi
```

Kiểm tra:

- CPU
- RAM
- GPU
- NVIDIA driver
- CUDA
- Docker
- Docker Compose
- disk
- network.

Đối chiếu với yêu cầu của Vexa hiện tại.

Không tự cài package nếu chưa kiểm tra environment.

---

# 6. PHASE 2 — CLONE VEXA

Clone:

```bash
git clone https://github.com/Vexa-ai/vexa.git
cd vexa
```

Kiểm tra:

```bash
git status
git branch
git log -1 --oneline
git tag --sort=-version:refname | head
```

Xác định:

- stable release
- current branch
- commit
- version
- breaking changes.

Không bắt đầu sửa source.

---

# 7. PHASE 3 — RUN VEXA

Ưu tiên:

```bash
make all
```

Không dùng `make dev` ở bước đầu.

Sau đó:

```bash
docker compose ps
```

Kiểm tra các service.

Nếu lỗi:

```bash
docker compose logs <service>
```

Phải xác định root cause.

Không giải quyết lỗi bằng cách:

- disable security
- bỏ authentication
- hard-code secret
- xoá service
- bỏ health check.

---

# 8. PHASE 4 — UNDERSTAND VEXA ARCHITECTURE

Phải xác định từ source code:

```text
Gateway
Meeting API
Bot Manager
Runtime
Bot
Transcription
Redis
PostgreSQL
MinIO
```

Vẽ architecture thực tế của release đang sử dụng.

Đặc biệt xác định:

```text
POST /bots
GET /bots/status
GET /transcripts/...
DELETE /bots/...
```

Nhưng chỉ sử dụng endpoint nếu source hiện tại xác nhận tồn tại.

---

# 9. PHASE 5 — VEXA API

Tạo biến:

```bash
export API_BASE=...
export API_KEY=...
```

Không commit secret.

Test:

```text
Health
Authentication
Bot creation
Bot status
Transcript
Bot termination
```

Tạo Python client:

```text
vexa_client.py
```

API client phải có:

```python
start_bot()
get_bot_status()
get_transcript()
stop_bot()
```

Response phải dùng schema thực tế của Vexa release hiện tại.

---

# 10. PHASE 6 — JITSI INTEGRATION

Tạo Jitsi test room.

Ví dụ:

```text
https://meet.jit.si/test-vexa-2026
```

Tách:

```text
Jitsi host
+
native meeting ID
```

Gọi Vexa Bot API.

Expected flow:

```text
POST /bots
     │
     ▼
Vexa Gateway
     │
     ▼
Bot Runtime
     │
     ▼
Vexa Bot
     │
     ▼
Jitsi
```

Verify:

### CHECKPOINT A

- Bot created.
- Bot container running.
- Bot connects.
- Bot joins Jitsi.
- Bot remains connected.
- Bot captures audio.

Chỉ khi A pass mới sang transcript.

---

# 11. PHASE 7 — TRANSCRIPTION

Test:

```text
Jitsi
 ↓
Vexa Bot
 ↓
Audio
 ↓
STT
 ↓
Transcript
```

Kiểm tra:

- text
- speaker
- timestamp
- start
- end
- confidence nếu có
- participant metadata nếu có.

Expected conceptual structure:

```json
{
  "speaker": "participant_01",
  "text": "Hello everyone",
  "start": 10.2,
  "end": 13.4
}
```

Schema cuối cùng phải lấy từ response thực tế.

### CHECKPOINT B

Phải chứng minh:

```text
Audio
 ↓
STT
 ↓
Transcript
```

hoạt động.

---

# 12. PHASE 8 — SPEAKER ATTRIBUTION

Mục tiêu:

```text
Speaker A
    ↓
Audio
    ↓
Transcript A

Speaker B
    ↓
Audio
    ↓
Transcript B
```

Xác định chính xác Vexa đang cung cấp:

- participant ID
- speaker ID
- display name
- diarization
- timestamps
- mapping giữa participant và transcript.

Không tự gọi `speaker_1`, `speaker_2` nếu hệ thống đã có participant identity.

### CHECKPOINT C

Phải mapping được:

```text
Participant
      ↓
Speaker
      ↓
Transcript
```

---

# 13. PHASE 9 — REALTIME

Nghiên cứu source hiện tại để xác định realtime mechanism:

```text
WebSocket
Redis stream
Polling
Internal event
API
```

Không giả định WebSocket tồn tại.

Nếu Vexa chưa expose public realtime interface phù hợp, xây:

```text
Vexa
  ↓
Our Backend
  ↓
WebSocket
  ↓
Chrome Extension
```

Backend phải xử lý:

- reconnect
- heartbeat
- duplicate events
- ordering
- connection lifecycle
- meeting lifecycle.

Event model:

```text
meeting.started
meeting.ended
participant.joined
participant.left
transcript.created
transcript.updated
ai.analysis.created
```

---

# 14. PHASE 10 — FASTAPI BACKEND

Tạo:

```text
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   ├── services/
│   │   ├── vexa.py
│   │   ├── transcript.py
│   │   ├── websocket.py
│   │   └── ai.py
│   ├── models/
│   └── schemas/
├── tests/
├── Dockerfile
├── requirements.txt
└── .env.example
```

API:

```text
POST /meeting/start
GET  /meeting/status
GET  /meeting/transcript
POST /meeting/stop
WS   /meeting/{meeting_id}/stream
POST /ai/analyze
```

Backend giữ:

```text
VEXA_API_KEY
```

---

# 15. DATABASE

PostgreSQL tables:

## meetings

```text
id
platform
native_meeting_id
started_at
ended_at
status
```

## participants

```text
id
meeting_id
participant_id
display_name
joined_at
left_at
```

## transcript_segments

```text
id
meeting_id
participant_id
speaker_id
start_time
end_time
text
confidence
created_at
```

## ai_analysis

```text
id
meeting_id
participant_id
model
result
confidence
created_at
```

## action_items

```text
id
meeting_id
owner
task
deadline
status
created_at
```

---

# 16. REDIS

Redis dùng cho:

```text
Realtime transcript
Event bus
WebSocket fan-out
Meeting state
Temporary cache
```

Không dùng PostgreSQL làm realtime message broker.

---

# 17. PHASE 11 — AI PIPELINE

Sau khi transcript hoạt động ổn định mới thêm AI.

Pipeline:

```text
Transcript
    │
    ▼
Normalization
    │
    ▼
Speaker-aware Chunking
    │
    ├──────────────┐
    ▼              ▼
 PhoBERT         Local LLM
    │              │
    ▼              ▼
Classification   Reasoning
    │              │
    └───────┬──────┘
            ▼
       AI Analysis
```

AI stack có thể gồm:

```text
faster-whisper
pyannote
PhoBERT
Ollama
Embedding model
```

Ưu tiên local AI nếu khả thi.

---

# 18. AI FEATURES

## 18.1 Live Transcript

```text
[Nguyễn A]
Em sẽ hoàn thành ETL thứ sáu.
```

## 18.2 Summary

```text
Meeting Summary
- ...
- ...
- ...
```

## 18.3 Action Items

```text
Task
Owner
Deadline
Status
```

## 18.4 Topic Detection

```text
Data Engineering
ETL
Testing
Deployment
```

## 18.5 Risk Analysis

Model có thể trả:

```json
{
  "label": "...",
  "score": 0.72,
  "confidence": 0.81,
  "evidence": [...]
}
```

Nếu risk analysis liên quan sức khỏe/tâm lý:

- không coi model output là diagnosis
- phải ghi rõ đây là model prediction/risk signal
- lưu evidence và confidence
- tránh đưa ra kết luận y khoa.

---

# 19. PHASE 12 — CHROME EXTENSION

Manifest V3.

Structure:

```text
extension/
├── manifest.json
├── background/
├── content/
├── popup/
├── meeting/
├── services/
└── ui/
```

Extension:

```text
Detect Jitsi
    ↓
Extract meeting identity
    ↓
Call Backend
    ↓
Start Vexa Bot
    ↓
Receive transcript
    ↓
Display transcript
    ↓
Display AI analysis
```

Không truy cập Vexa API key.

---

# 20. EXTENSION UI

Thiết kế panel:

```text
┌──────────────────────────────────┐
│       AI Meeting Assistant       │
├──────────────────────────────────┤
│ ● Connected                      │
│                                  │
│ Nguyễn A                         │
│ "Em sẽ hoàn thành ETL thứ sáu."  │
│                                  │
│ Nguyễn B                         │
│ "Em phụ trách testing."          │
├──────────────────────────────────┤
│ AI ANALYSIS                      │
│                                  │
│ Topic: Data Engineering          │
│                                  │
│ Action: Complete ETL              │
│ Owner: Nguyễn A                  │
│ Deadline: Friday                 │
│                                  │
│ Risk: Model result               │
└──────────────────────────────────┘
```

UI không được block meeting interface.

---

# 21. AUDIO ARCHITECTURE DECISION

Không bắt đầu bằng cách hack:

```text
DOM
 ↓
HTML audio element
```

Phải phân tích đúng tầng:

```text
Jitsi
 ↓
WebRTC
 ↓
MediaStream
 ↓
Audio Track
```

Tuy nhiên, nếu Vexa đã capture audio ở infrastructure layer thì **ưu tiên Vexa**, không capture audio lần thứ hai từ browser.

Mục tiêu:

```text
Jitsi
 ↓
Vexa
 ↓
Audio
```

thay vì:

```text
Jitsi
 ├── Vexa
 └── Browser Extension capture
```

trừ khi có yêu cầu đặc biệt.

---

# 22. SELF-HOSTED AI

Sau khi PoC hoàn chỉnh:

```text
Jitsi
 ↓
Vexa
 ↓
STT
 ↓
Backend
 ↓
Local GPU
```

AI server:

```text
GPU
├── faster-whisper
├── pyannote
├── PhoBERT
└── Ollama
```

LLM:

```text
Ollama
├── Qwen
├── Gemma
└── Mistral
```

Model phải được lựa chọn dựa trên:

- GPU VRAM
- latency
- Vietnamese performance
- context length
- quantization.

Không tải model lớn nếu hardware không phù hợp.

---

# 23. SECURITY

Implement:

```text
HTTPS
JWT/session
CORS
WebSocket authentication
API key isolation
Secret management
Meeting access control
Transcript access control
Data retention
Audit logging
```

Không log:

```text
API key
JWT
password
private transcript
```

nếu không cần thiết.

---

# 24. OBSERVABILITY

Structured logs:

```text
request_id
meeting_id
bot_id
participant_id
event
timestamp
latency
status
```

Metrics:

```text
bot_join_success
bot_join_latency
transcription_latency
transcript_segments
speaker_mapping_accuracy
ai_inference_latency
websocket_connections
error_rate
```

---

# 25. TESTING

Phải có:

```text
Unit Tests
Integration Tests
API Tests
WebSocket Tests
E2E Tests
```

E2E:

```text
User opens Jitsi
       ↓
Extension detects meeting
       ↓
Backend starts Vexa
       ↓
Vexa Bot joins Jitsi
       ↓
Audio captured
       ↓
STT
       ↓
Speaker attribution
       ↓
Transcript
       ↓
Backend
       ↓
AI
       ↓
Extension
       ↓
Result displayed
```

---

# 26. TROUBLESHOOTING STRATEGY

Khi lỗi:

## Step 1

Xác định layer:

```text
Jitsi
Vexa
Bot
Audio
STT
API
Backend
WebSocket
AI
Extension
```

## Step 2

Collect logs.

## Step 3

Reproduce.

## Step 4

Root cause.

## Step 5

Minimal fix.

## Step 6

Regression test.

Không sửa nhiều component cùng lúc.

---

# 27. GIT STRATEGY

Tạo commit theo phase:

```text
feat: setup vexa environment
feat: integrate vexa api
feat: integrate jitsi bot
feat: add transcript service
feat: add realtime transcript
feat: add fastapi backend
feat: add ai analysis
feat: add chrome extension
test: add end to end meeting flow
```

Không commit:

```text
.env
API keys
passwords
private certificates
```

---

# 28. DOCUMENTATION

Cuối project phải có:

```text
README.md
ARCHITECTURE.md
DEPLOYMENT.md
API.md
JITSI.md
VEXA.md
AI_PIPELINE.md
EXTENSION.md
TROUBLESHOOTING.md
SECURITY.md
```

Architecture diagram phải thể hiện:

```text
Jitsi
 ↓
Vexa
 ↓
Transcript
 ↓
Backend
 ↓
AI
 ↓
Extension
```

---

# 29. FINAL ACCEPTANCE CRITERIA

Project chỉ được coi là hoàn thành khi:

### Infrastructure

```text
Vexa running
Docker healthy
API accessible
```

### Jitsi

```text
Bot can join
Bot can stay connected
Audio available
```

### Transcript

```text
Transcript generated
Timestamp available
Speaker mapping available
```

### Backend

```text
FastAPI running
Vexa integrated
WebSocket working
Database working
Redis working
```

### AI

```text
PhoBERT working
LLM working
Summary working
Action extraction working
Risk analysis working
```

### Extension

```text
Jitsi detected
Meeting started
Transcript displayed
AI result displayed
```

### Security

```text
API key never exposed
Secrets excluded from Git
WebSocket authenticated
```

---

# 30. WORKING MODE

Đây là yêu cầu quan trọng nhất.

**Không trả lời bằng một tutorial dài và yêu cầu tôi tự thực hiện tất cả.**

Bạn phải làm việc theo dạng interactive session.

Mỗi lượt chỉ thực hiện một checkpoint hợp lý.

Format:

```text
CURRENT PHASE
PHASE X — ...

OBJECTIVE
...

COMMAND
...

EXPECTED RESULT
...

WHAT TO SEND BACK
...
```

Tôi sẽ chạy command và gửi output.

Sau đó bạn:

1. phân tích output;
2. xác định pass/fail;
3. sửa lỗi nếu có;
4. đưa command tiếp theo;
5. cập nhật progress.

Không nhảy sang phase tiếp theo khi checkpoint hiện tại chưa pass.

---

# 31. START NOW

Bắt đầu bằng:

```text
PHASE 1 — Environment Audit
```

Không cài Vexa ngay.

Trước tiên hãy yêu cầu tôi chạy các command kiểm tra:

```bash
uname -a
lsb_release -a
docker --version
docker compose version
git --version
make --version
nvidia-smi
free -h
df -h
```

Sau khi nhận kết quả:

1. đánh giá environment;
2. xác định compatibility;
3. đưa ra PHASE 2;
4. hướng dẫn clone Vexa;
5. xác định release phù hợp;
6. sau đó mới chạy `make all`.

Mục tiêu đầu tiên cần đạt:

```text
Jitsi
  ↓
Vexa Bot
  ↓
Transcript
```

Chưa triển khai AI và Chrome Extension cho đến khi pipeline trên hoạt động ổn định.

# END SESSION
