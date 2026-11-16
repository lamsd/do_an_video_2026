# Test report — 2026-11-16

| Command | Exit code | Result |
|---|---:|---|
| `.venv/bin/python -m pytest -q` | 0 | 7 passed in 0.24s |
| `.venv/bin/ruff check app tests tools` | 0 | All checks passed |
| `tools/evaluate_sentiment.py ...` | 0 | Smoke test wrote JSON result |

Phạm vi unit test hiện gồm chuẩn hóa/quality gate, ghép unit, classifier contract và
ngữ nghĩa abstention `unknown`. Không có Docker/PostgreSQL/Valkey/Jitsi đang chạy
trong lần này; mọi assertion E2E vì thế là **NOT RUN**, không phải PASS.
