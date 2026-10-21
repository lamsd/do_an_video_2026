# Jitsi Multi-Agent Emotion Research Lab

A runnable research prototype where four AI personas hold a bounded, turn-based discussion, synthesize one audio artifact per turn, extract acoustic features, and expose an Ubuntu/Jitsi virtual-microphone workflow. It is deliberately scoped for synthetic research experiments — **not clinical diagnosis, depression screening, or participant surveillance**.

## What is implemented

- Four fixed personas with independent instructions and configured voices: Empathy (`nova`), Critical (`onyx`), Optimistic (`coral`), Moderator (`sage`).
- A bounded orchestrator: `Empathy → Critical → Optimistic → Moderator`, repeated for the requested number of rounds. One task emits one turn at a time, preventing overlapping generated speech.
- OpenAI Responses and TTS adapters when `OPENAI_API_KEY` is configured. Without a key, the app runs in a clearly labeled offline-template / placeholder-tone mode so the dashboard and audio pipeline can be tested without presenting a tone as speech.
- WAV normalization and versioned acoustic extraction: duration, sample rate, RMS, ZCR, pitch, spectral centroid/bandwidth, MFCC, and Mel-spectrogram.
- An emotion interface that returns `unavailable` until a separately evaluated checkpoint **and** model version are configured. It does not make up model performance or infer depression.
- FastAPI API, PostgreSQL persistence, React/TypeScript dashboard, JSON/CSV exports, and PulseAudio/PipeWire Jitsi scripts.

## Run with Docker Compose

```bash
cd jitsi-multi-agent-emotion-lab
cp .env.example .env
# Add OPENAI_API_KEY to .env for actual GPT + OpenAI TTS generation.
docker compose up --build
```

Open the dashboard at [http://localhost:5173](http://localhost:5173), then use `http://localhost:8000/docs` for the API contract. PostgreSQL is retained in the `emotion-lab-postgres` named volume; generated artifacts are bind-mounted to `data/media/` and ignored by Git.

To stop while retaining database data:

```bash
docker compose down
```

Do not use `docker compose down -v` unless deleting the experiment database is intentional.

## Run the backend locally

Python 3.11+ is required. The default `DATABASE_URL` is a local SQLite file, useful for development/tests; Compose uses PostgreSQL.

```bash
cd jitsi-multi-agent-emotion-lab
uv venv
uv pip install -e '.[dev]'
uv run --directory . uvicorn app.main:app --app-dir backend --reload
```

In another terminal:

```bash
cd jitsi-multi-agent-emotion-lab/frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL=http://localhost:8000` if the frontend is served separately. The React client polls only the active experiment and never receives an API key.

## Main API

| Endpoint | Purpose |
| --- | --- |
| `POST /api/sessions` | Create and begin a bounded discussion. |
| `POST /api/sessions/{id}/pause`, `/resume`, `/stop` | Control the orchestration lifecycle. |
| `POST /api/sessions/{id}/messages` | Add researcher context between turns. |
| `GET /api/sessions/{id}` | Poll timeline, audio metadata, features, and prediction state. |
| `GET /api/sessions/{id}/turns/{turn}/audio` | Retrieve a generated WAV. |
| `GET /api/sessions/{id}/export.json` / `export.csv` | Export reproducible experiment metadata. |

Each agent turn stores session/turn IDs, transcript, voice, requested style, timestamp, audio location, generation backend, and feature-extraction version. User messages are stored as contextual turns and never receive synthetic audio.

## Jitsi virtual microphone

The generated-audio MVP requires an Ubuntu desktop session and no physical microphone:

```bash
cd jitsi-multi-agent-emotion-lab
chmod +x scripts/*.sh
./scripts/setup_virtual_audio.sh
./scripts/check_virtual_audio.sh
./scripts/play_audio_to_jitsi.sh data/media/<session_id>/<turn_id>.wav
./scripts/cleanup_virtual_audio.sh
```

Select `JitsiLabMic` in the Jitsi browser's microphone settings. The playback script uses a lock, so generated agent WAVs are routed sequentially. Details and explicit limitations are in [docs/JITSI_INTEGRATION.md](docs/JITSI_INTEGRATION.md).

## Emotion model contract

`backend/app/emotion/classifier.py` is a strict gateway, not a claimed trained classifier. Set both below only after independently training and evaluating a model with a licensed human-labelled corpus such as RAVDESS or CREMA-D:

```dotenv
EMOTION_CHECKPOINT=/secure/models/evaluated-emotion-model.pt
EMOTION_MODEL_VERSION=ravdess-baseline-2026-10-20
```

The checkpoint adapter currently abstains unless an explicit validated inference head is registered. This makes it impossible for the dashboard to silently turn acoustic descriptors or a TTS style into a purported emotion result.

## Quality checks

```bash
cd jitsi-multi-agent-emotion-lab
uv run pytest
uv run ruff check .
uv run mypy backend/app
cd frontend && npm run build
```

Read [docs/RESEARCH_AND_DATA_GUARDRAILS.md](docs/RESEARCH_AND_DATA_GUARDRAILS.md) before using human participants or any real recordings.

## Deliberate non-claims

- No physical microphone is required for the synthetic-audio MVP.
- Four independent Jitsi bots are not implemented.
- The Jitsi IFrame API is not presented as a raw participant-audio interface.
- No accuracy, emotion score, depression risk, or clinical conclusion is fabricated.
- Human recordings, API keys, checkpoints, and generated WAVs are not committed to Git.

