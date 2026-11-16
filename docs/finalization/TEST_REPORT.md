# Test report — 2026-11-16

| Command | Exit code | Result |
|---|---:|---|
| `cd source/src/backend && .venv/bin/python -m pytest -q` | 0 | 46 passed |
| `cd source/src/backend && .venv/bin/ruff check app tests` | 0 | All checks passed |
| `cd source && sh -n scripts/smoke-analysis-pipeline.sh` | 0 | Shell syntax valid |
| `cd source && ./scripts/verify.sh` | 0 | Backend and Dashboard reachable |
| `cd source && ./scripts/smoke-analysis-pipeline.sh` | 0 | Synthetic API → Valkey → worker checks passed |

Phạm vi mới gồm quality gate, ghép unit, classifier contract, coverage, immutable
snapshot, Valkey pending-job reclaim và SSE cursor. Smoke test dùng PostgreSQL,
Valkey và worker đang chạy, tạo rồi xóa một fixture synthetic. Đây không phải Jitsi
E2E, forced worker crash, đánh giá ASR hoặc đánh giá chất lượng sentiment.
