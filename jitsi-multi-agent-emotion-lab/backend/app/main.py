from __future__ import annotations

import asyncio
import csv
import io
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.orchestrator import DiscussionOrchestrator
from app.agents.profiles import AGENT_PROFILES
from app.config import Settings, get_settings
from app.db import Base, SessionLocal, engine, get_db
from app.models import DiscussionSession, DiscussionTurn
from app.schemas import (
    AddUserMessageRequest,
    AgentProfileOut,
    AudioAnalysisOut,
    CreateSessionRequest,
    SessionOut,
    TurnOut,
)


class RunRegistry:
    def __init__(self, orchestrator: DiscussionOrchestrator):
        self.orchestrator = orchestrator
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def start(self, session_id: str) -> None:
        active = self.tasks.get(session_id)
        if active and not active.done():
            return
        task = asyncio.create_task(self.orchestrator.run(session_id))
        self.tasks[session_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(session_id, None))

    async def close(self) -> None:
        for task in self.tasks.values():
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.media_root.mkdir(parents=True, exist_ok=True)
    # SQLite needs its parent directory when running locally without Docker.
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url.removeprefix("sqlite:///")) .parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    app.state.settings = settings
    app.state.registry = RunRegistry(DiscussionOrchestrator(settings, SessionLocal))
    yield
    await app.state.registry.close()


app = FastAPI(
    title="Jitsi Multi-Agent Emotion Research Lab",
    version="0.1.0",
    description=(
        "Research prototype for synthetic multi-agent discussions. It is not a clinical or depression "
        "assessment system."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().parsed_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _turn_out(turn: DiscussionTurn) -> TurnOut:
    return TurnOut(
        id=turn.id,
        sequence=turn.sequence,
        round_number=turn.round_number,
        speaker_type=turn.speaker_type,
        agent_id=turn.agent_id,
        transcript=turn.transcript,
        voice=turn.voice,
        intended_style=turn.intended_style,
        audio_url=(f"/api/sessions/{turn.session_id}/turns/{turn.id}/audio" if turn.audio_file_path else None),
        generation_backend=turn.generation_backend,
        feature_extraction_version=turn.feature_extraction_version,
        features=turn.features,
        emotion_prediction=turn.emotion_prediction,
        created_at=turn.created_at,
    )


def _session_out(record: DiscussionSession, include_turns: bool = True) -> SessionOut:
    turns = [_turn_out(turn) for turn in record.turns] if include_turns else []
    return SessionOut(
        id=record.id,
        topic=record.topic,
        requested_rounds=record.requested_rounds,
        completed_rounds=record.completed_rounds,
        status=record.status,  # type: ignore[arg-type]
        created_at=record.created_at,
        updated_at=record.updated_at,
        turns=turns,
    )


def _load_session(db: Session, session_id: str) -> DiscussionSession:
    record = db.scalars(
        select(DiscussionSession)
        .where(DiscussionSession.id == session_id)
        .options()
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Discussion session not found")
    # Relationship is lazy-loaded while this request session is alive.
    return record


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "jitsi-multi-agent-emotion-lab",
        "openai_configured": bool(settings.openai_api_key),
        "clinical_use": "not supported",
    }


@app.get("/api/agents", response_model=list[AgentProfileOut])
def list_agents() -> list[AgentProfileOut]:
    return [
        AgentProfileOut(
            id=profile.id,
            label=profile.label,
            personality=profile.personality,
            voice=profile.voice,
            speaking_style=profile.speaking_style,
        )
        for profile in AGENT_PROFILES
    ]


@app.post("/api/sessions", response_model=SessionOut, status_code=201)
def create_session(payload: CreateSessionRequest, db: Session = Depends(get_db)) -> SessionOut:
    record = DiscussionSession(topic=payload.topic.strip(), requested_rounds=payload.rounds, status="created")
    db.add(record)
    db.commit()
    db.refresh(record)
    app.state.registry.start(record.id)
    return _session_out(record, include_turns=False)


@app.get("/api/sessions", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db)) -> list[SessionOut]:
    records = db.scalars(select(DiscussionSession).order_by(DiscussionSession.created_at.desc())).all()
    return [_session_out(record, include_turns=False) for record in records]


@app.get("/api/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: Session = Depends(get_db)) -> SessionOut:
    return _session_out(_load_session(db, session_id))


@app.post("/api/sessions/{session_id}/pause", response_model=SessionOut)
def pause_session(session_id: str, db: Session = Depends(get_db)) -> SessionOut:
    record = _load_session(db, session_id)
    if record.status == "running":
        record.status = "paused"
        db.commit()
        db.refresh(record)
    return _session_out(record)


@app.post("/api/sessions/{session_id}/resume", response_model=SessionOut)
def resume_session(session_id: str, db: Session = Depends(get_db)) -> SessionOut:
    record = _load_session(db, session_id)
    if record.status == "paused":
        record.status = "created"
        db.commit()
        db.refresh(record)
        app.state.registry.start(record.id)
    return _session_out(record)


@app.post("/api/sessions/{session_id}/stop", response_model=SessionOut)
def stop_session(session_id: str, db: Session = Depends(get_db)) -> SessionOut:
    record = _load_session(db, session_id)
    if record.status not in {"completed", "failed"}:
        record.status = "stopped"
        db.commit()
        db.refresh(record)
    return _session_out(record)


@app.post("/api/sessions/{session_id}/messages", response_model=SessionOut)
def add_user_message(
    session_id: str, payload: AddUserMessageRequest, db: Session = Depends(get_db)
) -> SessionOut:
    record = _load_session(db, session_id)
    sequence = len(record.turns) + 1
    db.add(
        DiscussionTurn(
            session_id=record.id,
            sequence=sequence,
            round_number=record.completed_rounds + 1,
            speaker_type="user",
            transcript=payload.message.strip(),
        )
    )
    db.commit()
    db.refresh(record)
    return _session_out(record)


@app.get("/api/sessions/{session_id}/turns/{turn_id}/analysis", response_model=AudioAnalysisOut)
def get_analysis(session_id: str, turn_id: str, db: Session = Depends(get_db)) -> AudioAnalysisOut:
    turn = db.get(DiscussionTurn, turn_id)
    if not turn or turn.session_id != session_id or not turn.features:
        raise HTTPException(status_code=404, detail="Audio analysis not found")
    return AudioAnalysisOut(
        session_id=session_id,
        turn_id=turn_id,
        features=turn.features,
        emotion_prediction=turn.emotion_prediction or {"status": "unavailable"},
    )


@app.get("/api/sessions/{session_id}/turns/{turn_id}/audio")
def get_audio(session_id: str, turn_id: str, db: Session = Depends(get_db)) -> FileResponse:
    turn = db.get(DiscussionTurn, turn_id)
    if not turn or turn.session_id != session_id or not turn.audio_file_path:
        raise HTTPException(status_code=404, detail="Audio sample not found")
    path = Path(turn.audio_file_path).resolve()
    media_root = app.state.settings.media_root.resolve()
    if media_root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio sample is unavailable")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@app.get("/api/sessions/{session_id}/export.json")
def export_json(session_id: str, db: Session = Depends(get_db)) -> Response:
    payload = _session_out(_load_session(db, session_id)).model_dump(mode="json")
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{session_id}.json"'},
    )


@app.get("/api/sessions/{session_id}/export.csv")
def export_csv(session_id: str, db: Session = Depends(get_db)) -> Response:
    record = _load_session(db, session_id)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        [
            "session_id",
            "turn_id",
            "sequence",
            "round",
            "speaker_type",
            "agent_id",
            "voice",
            "intended_style",
            "transcript",
            "audio_file_path",
            "feature_extraction_version",
            "emotion_status",
            "emotion_label",
        ]
    )
    for turn in record.turns:
        prediction = turn.emotion_prediction or {}
        writer.writerow(
            [
                record.id,
                turn.id,
                turn.sequence,
                turn.round_number,
                turn.speaker_type,
                turn.agent_id,
                turn.voice,
                turn.intended_style,
                turn.transcript,
                turn.audio_file_path,
                turn.feature_extraction_version,
                prediction.get("status"),
                prediction.get("label"),
            ]
        )
    return Response(
        stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{session_id}.csv"'},
    )


@app.get("/api/jitsi/diagnostics")
def jitsi_diagnostics() -> dict[str, str]:
    return {
        "status": "host-check-required",
        "virtual_microphone": "Run scripts/check_virtual_audio.sh on the Ubuntu host.",
        "playback_queue": "Use scripts/play_audio_to_jitsi.sh sequentially for generated WAVs.",
        "limitation": "The Jitsi IFrame API does not expose raw participant audio tracks.",
    }

