# Evidence manifest template (redacted)

Không commit audio, transcript cá nhân, API key, webhook secret, meeting URL hoặc
định danh người tham gia. Mỗi buổi consent tạo một bản manifest riêng ở kho lưu
trữ được phê duyệt.

| Field | Value |
|---|---|
| Git commit | `<commit>` |
| Date/time/timezone | `<ISO-8601>` |
| Consent recorded | `<reference, not content>` |
| Participants | `2 users + 1 bot` |
| Runtime | `Jitsi → Vexa/local STT → FastAPI/PostgreSQL/Valkey → worker → Dashboard/SSE` |
| Model / preprocessing | `baseline-rules-v3` / `2026-11-stt-quality-gate-v2` |
| Meeting/run/revision | `<redacted stable references>` |
| Commands and exit codes | `<paths to redacted logs>` |
| API/DB/UI snapshots | `<redacted artifact paths>` |
| Result | `PASS / FAIL / NOT RUN` |
