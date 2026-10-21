from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker import MqttBridge
from app.config import Settings, get_settings
from app.coordinator import TurnCoordinator
from app.db import Base, SessionLocal, engine, get_db
from app.identities import AGENTS
from app.models import DeviceStatus, ExperimentSession, ExperimentTurn
from app.schemas import DeviceOut, SessionOut, StartExperimentRequest, TurnOut


def _seed_devices() -> None:
    with SessionLocal() as db:
        for agent in AGENTS:
            if not db.get(DeviceStatus, agent.agent_id):
                db.add(DeviceStatus(agent_id=agent.agent_id, device_id=agent.device_id, state="disconnected"))
        db.commit()


async def _liveness_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(5)
        app.state.coordinator.mark_stale_devices()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.media_root.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        database_file = Path(settings.database_url.removeprefix("sqlite:///"))
        database_file.parent.mkdir(parents=True, exist_ok=True)
    # Docker/PostgreSQL is migrated by Alembic before Uvicorn starts. Keeping this narrow
    # bootstrap path makes isolated SQLite simulator/test runs convenient without bypassing
    # production migrations.
    if settings.database_url.startswith("sqlite:///"):
        Base.metadata.create_all(bind=engine)
    _seed_devices()
    coordinator = TurnCoordinator(settings, SessionLocal)
    app.state.settings = settings
    app.state.coordinator = coordinator
    app.state.bridge = None
    if settings.mqtt_backend_password:
        bridge = MqttBridge(settings, coordinator.handle_message)
        coordinator.attach_publisher(bridge)
        bridge.start()
        app.state.bridge = bridge
    liveness_task = asyncio.create_task(_liveness_loop(app))
    try:
        yield
    finally:
        liveness_task.cancel()
        await asyncio.gather(liveness_task, return_exceptions=True)
        if app.state.bridge:
            app.state.bridge.close()


app = FastAPI(
    title="Phòng thí nghiệm họp AI phân tán ESP32",
    version="0.1.0",
    description=(
        "Mô phỏng nghiên cứu thảo luận MQTT tự hành bằng bốn ESP32. Kết quả âm thanh tổng hợp "
        "không phải đánh giá lâm sàng hoặc trầm cảm."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _turn_out(turn: ExperimentTurn) -> TurnOut:
    return TurnOut(
        id=turn.id,
        agent_id=turn.agent_id,
        sequence=turn.sequence,
        round_number=turn.round_number,
        transcript=turn.transcript,
        voice=turn.voice,
        audio_url=(f"/api/sessions/{turn.session_id}/turns/{turn.id}/audio" if turn.audio_file_path else None),
        acoustic_metadata=turn.acoustic_metadata,
        emotion_prediction=turn.emotion_prediction,
        created_at=turn.created_at,
    )


def _session_out(session: ExperimentSession, with_turns: bool = True) -> SessionOut:
    return SessionOut(
        id=session.id,
        topic=session.topic,
        requested_rounds=session.requested_rounds,
        completed_rounds=session.completed_rounds,
        status=session.status,  # type: ignore[arg-type]
        created_at=session.created_at,
        updated_at=session.updated_at,
        turns=[_turn_out(turn) for turn in session.turns] if with_turns else [],
    )


def _session_or_404(db: Session, session_id: str) -> ExperimentSession:
    session = db.get(ExperimentSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Experiment session not found")
    return session


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "status": "ok",
        "mqtt_configured": bool(settings.mqtt_backend_password),
        "openai_configured": bool(settings.openai_api_key),
        "hardware_model": "four fixed ESP32 devices; no microphones or speakers",
    }


@app.get("/api/agents")
def agents() -> list[dict[str, str]]:
    return [
        {
            "agent_id": agent.agent_id,
            "device_id": agent.device_id,
            "display_name": agent.display_name,
            "meeting_participant_id": agent.meeting_participant_id,
            "voice": agent.voice,
            "personality": agent.personality,
            "speaking_style": agent.speaking_style,
        }
        for agent in AGENTS
    ]


@app.get("/api/devices", response_model=list[DeviceOut])
def devices(db: Session = Depends(get_db)) -> list[DeviceOut]:
    records = {record.agent_id: record for record in db.scalars(select(DeviceStatus)).all()}
    return [
        DeviceOut(
            agent_id=agent.agent_id,
            device_id=agent.device_id,
            display_name=agent.display_name,
            voice=agent.voice,
            state=records[agent.agent_id].state,
            firmware_version=records[agent.agent_id].firmware_version,
            last_seen_at=records[agent.agent_id].last_seen_at,
            last_error=records[agent.agent_id].last_error,
        )
        for agent in AGENTS
    ]


@app.post("/api/sessions", response_model=SessionOut, status_code=201)
def start_session(payload: StartExperimentRequest, db: Session = Depends(get_db)) -> SessionOut:
    if not app.state.bridge:
        raise HTTPException(status_code=503, detail="MQTT coordinator is not connected")
    try:
        session = app.state.coordinator.start(payload.topic, payload.rounds)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    # Reload in the request session to keep response handling separate from the coordinator session.
    return _session_out(_session_or_404(db, session.id), with_turns=False)


@app.get("/api/sessions", response_model=list[SessionOut])
def sessions(db: Session = Depends(get_db)) -> list[SessionOut]:
    records = db.scalars(select(ExperimentSession).order_by(ExperimentSession.created_at.desc())).all()
    return [_session_out(record, with_turns=False) for record in records]


@app.get("/api/sessions/{session_id}", response_model=SessionOut)
def session(session_id: str, db: Session = Depends(get_db)) -> SessionOut:
    return _session_out(_session_or_404(db, session_id))


@app.post("/api/sessions/{session_id}/stop", response_model=SessionOut)
def stop_session(session_id: str, db: Session = Depends(get_db)) -> SessionOut:
    try:
        app.state.coordinator.stop(session_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _session_out(_session_or_404(db, session_id))


@app.post("/api/sessions/{session_id}/pause", response_model=SessionOut)
def pause_session(session_id: str, db: Session = Depends(get_db)) -> SessionOut:
    try:
        app.state.coordinator.pause(session_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _session_out(_session_or_404(db, session_id))


@app.post("/api/sessions/{session_id}/resume", response_model=SessionOut)
def resume_session(session_id: str, db: Session = Depends(get_db)) -> SessionOut:
    try:
        app.state.coordinator.resume(session_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _session_out(_session_or_404(db, session_id))


@app.get("/api/sessions/{session_id}/turns/{turn_id}/audio")
def audio(session_id: str, turn_id: str, db: Session = Depends(get_db)) -> FileResponse:
    turn = db.get(ExperimentTurn, turn_id)
    if not turn or turn.session_id != session_id or not turn.audio_file_path:
        raise HTTPException(status_code=404, detail="Audio artifact was not found")
    path = Path(turn.audio_file_path).resolve()
    media_root = app.state.settings.media_root.resolve()
    if media_root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio artifact is unavailable")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@app.get("/api/meeting/adapter-status")
def meeting_adapter_status() -> dict[str, str]:
    return {
        "status": "interface-only",
        "limitation": (
            "Four live Jitsi virtual participants require a media-capable bot/transport adapter; "
            "the Jitsi IFrame API alone does not expose raw audio tracks."
        ),
        "implemented_now": "per-agent identity and per-turn WAV artifact contract",
    }

