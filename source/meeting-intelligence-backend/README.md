# Meeting Intelligence Backend

FastAPI backend nhận transcript Vexa, lưu application-owned PostgreSQL, phục vụ transcript cho UI qua REST/SSE và nhận webhook end-call có HMAC.

## Current scope

- Google Meet URL → Vexa bot spawn (server-side API key).
- REST transcript reconciliation và persisted segments.
- SSE event stream for near-realtime UI.
- Signed Vexa terminal webhook dedupe/finalization.

Vexa `/ws` direct ingestion là phase kế tiếp; polling REST vẫn là fallback dữ liệu chuẩn của MVP.

## AI analysis architecture

The repository separates HTTP/SSE serving from AI processing:

```text
backend (FastAPI) → PostgreSQL + Valkey Stream → worker (sentiment pipeline)
                                          │
                                          └→ SSE event → dashboard
```

- `app/analysis/`: pure quality rules, analysis-unit builder, and a swappable classifier protocol.
- `app/repositories/analysis.py`: idempotent analysis-run persistence and aggregates.
- `app/workers/sentiment.py`: long-running Stream consumer, intentionally outside FastAPI.
- `app/api/analytics.py`: protected analytics/evidence endpoints.

The current classifier is a deterministic rule baseline (`baseline-rules-v1`) to validate the pipeline. It is deliberately not presented as a trained PhoBERT model. A PhoBERT adapter can replace it through `SentimentClassifier` after a versioned artifact and evaluation report exist.

### Run locally

Set the analysis settings in `.env` (defaults are defined in `app/config.py`), then start the complete CPU topology:

```bash
docker compose up -d --build
```

For a GPU worker host with NVIDIA Container Toolkit, start the optional override:

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
```

Request a run after transcript reconciliation:

```bash
curl -X POST 'http://localhost:8088/v1/meetings/<meeting-id>/analysis?kind=final' \
  -H 'X-App-User-Id: local-dev'
```

`<meeting-id>` is the application UUID returned by `POST /v1/meetings`; it is not a Google Meet room code such as `abc-defg-hij`. The dashboard validates this before making an API request.

The endpoints `/analytics/overview`, `/analytics/timeline`, and `/analytics/units` are nested under `/v1/meetings/<meeting-id>/`. See `../../TRANSCRIPT_AI_DATA_ANALYSIS.md` and `../../AI_SENTIMENT_ANALYSIS_DASHBOARD_PLAN.md` for the implementation contract and rollout gates.

The dashboard is served at `http://localhost:3000` by the `dashboard` Compose service. It is intentionally a framework-free MVP: it provides API-backed KPI cards, a time series, evidence rows, and SSE refresh without embedding secrets. Replace the temporary development identity with real session/JWT authentication before exposing it beyond localhost.

## Run

1. Vexa Compose phải đang tạo network `vexa-v012_vexa`.
2. Copy `.env.example` thành `.env`, điền `POSTGRES_PASSWORD`, `VEXA_API_KEY`, `VEXA_WEBHOOK_SECRET`.
3. Chạy:

```bash
docker compose up -d --build
curl http://localhost:8088/health
```

Backend gọi Vexa qua Docker DNS `http://gateway:8000`. Đọc `../BACKEND_REALTIME_GUIDE.md` để biết cấu hình webhook Vexa và runbook đầy đủ.
