from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.audio.pipeline import AudioPipeline, unavailable_emotion_prediction
from app.broker import MqttBridge
from app.config import Settings
from app.generation import AgentTextGenerator
from app.identities import AGENT_BY_ID, TURN_ORDER
from app.models import DeviceStatus, ExperimentSession, ExperimentTurn
from app.protocol import Envelope, topic_context, topic_device
from app.state import DeviceState

log = logging.getLogger(__name__)


class TurnCoordinator:
    """The sole authority that advances a bounded, tokenized discussion."""

    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]):
        self.settings = settings
        self.session_factory = session_factory
        self.publisher: MqttBridge | None = None
        self.generator = AgentTextGenerator(settings)
        self.audio = AudioPipeline(settings)
        self.lock = threading.RLock()
        # Text is remembered only until the owning ESP32 echoes it under its own topic.
        self.issued_responses: dict[str, str] = {}
        # A turn id is assigned before the grant and must accompany every turn-scoped message.
        self.issued_turn_ids: dict[str, str] = {}

    def attach_publisher(self, publisher: MqttBridge) -> None:
        self.publisher = publisher

    def handle_message(self, topic: str, message: Envelope) -> None:
        """Validate namespace/payload identity before accepting any device message."""
        parts = topic.split("/")
        if len(parts) < 4 or parts[:2] != ["lab", "device"]:
            return
        topic_agent = parts[2]
        suffix = "/".join(parts[3:])
        if message.agent_id != topic_agent or topic_agent not in AGENT_BY_ID:
            log.warning("Rejected MQTT identity mismatch on %s", topic)
            return
        with self.lock:
            if suffix == "register":
                self._register(topic_agent, message)
            elif suffix == "heartbeat":
                self._heartbeat(topic_agent, message)
            elif suffix == "generation/request":
                self._generation_request(topic_agent, message)
            elif suffix == "turn/published":
                self._turn_published(topic_agent, message)

    def start(self, topic: str, rounds: int) -> ExperimentSession:
        with self.lock, self.session_factory() as db:
            if not self._all_devices_online(db):
                raise ValueError("All four ESP32 devices must be online before a discussion can begin.")
            active = db.scalar(
                select(ExperimentSession).where(ExperimentSession.status.in_(["running", "paused"]))
            )
            if active:
                raise ValueError("An experiment is already running.")
            session = ExperimentSession(topic=topic.strip(), requested_rounds=rounds, status="running")
            db.add(session)
            db.commit()
            db.refresh(session)
            for agent_id in AGENT_BY_ID:
                self._publish_device_control(agent_id, {"event": "resume", "state": "ready"})
            self._publish_context(db, session)
            self._grant_expected_turn(db, session)
            return session

    def stop(self, session_id: str) -> ExperimentSession:
        with self.lock, self.session_factory() as db:
            session = self._session_or_error(db, session_id)
            if session.status in {"running", "paused"}:
                session.status = "stopped"
                if session.active_turn_token:
                    self.issued_responses.pop(session.active_turn_token, None)
                    self.issued_turn_ids.pop(session.active_turn_token, None)
                session.active_turn_token = None
                session.active_turn_id = None
                session.active_sequence_number = None
                db.commit()
                for agent_id in AGENT_BY_ID:
                    self._publish_device_control(agent_id, {"event": "stop", "state": "stopped"})
            return session

    def pause(self, session_id: str) -> ExperimentSession:
        with self.lock, self.session_factory() as db:
            session = self._session_or_error(db, session_id)
            if session.status != "running":
                raise ValueError("Only a running experiment can be paused.")
            session.status = "paused"
            if session.active_turn_token:
                self.issued_responses.pop(session.active_turn_token, None)
                self.issued_turn_ids.pop(session.active_turn_token, None)
            session.active_turn_token = None
            session.active_turn_id = None
            session.active_sequence_number = None
            db.commit()
            for agent_id in AGENT_BY_ID:
                self._publish_device_control(agent_id, {"event": "pause", "state": "paused"})
            return session

    def resume(self, session_id: str) -> ExperimentSession:
        with self.lock, self.session_factory() as db:
            session = self._session_or_error(db, session_id)
            if session.status != "paused":
                raise ValueError("Only a paused experiment can be resumed.")
            if not self._all_devices_online(db):
                raise ValueError("All four ESP32 devices must be online before resuming.")
            session.status = "running"
            db.commit()
            for agent_id in AGENT_BY_ID:
                self._publish_device_control(agent_id, {"event": "resume", "state": "ready"})
            self._publish_context(db, session)
            self._grant_expected_turn(db, session)
            return session

    def mark_stale_devices(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.heartbeat_ttl_seconds)
        with self.lock, self.session_factory() as db:
            changed = False
            for device in db.scalars(select(DeviceStatus)).all():
                seen = device.last_seen_at
                if seen and seen.tzinfo is None:
                    seen = seen.replace(tzinfo=UTC)
                if device.state != "disconnected" and (seen is None or seen < cutoff):
                    device.state = "disconnected"
                    device.last_error = "heartbeat timeout"
                    changed = True
            if changed:
                db.commit()

    def _register(self, agent_id: str, message: Envelope) -> None:
        agent = AGENT_BY_ID[agent_id]
        if message.device_id != agent.device_id:
            log.warning("Rejected %s: device identifier did not match fixed mapping", agent_id)
            return
        with self.session_factory() as db:
            device = db.get(DeviceStatus, agent_id) or DeviceStatus(
                agent_id=agent_id, device_id=agent.device_id
            )
            device.state = "ready"
            device.mqtt_client_id = str(message.payload.get("mqtt_client_id", ""))[:96] or None
            device.firmware_version = str(message.payload.get("firmware_version", ""))[:32] or None
            device.last_seen_at = datetime.now(UTC)
            device.last_error = None
            db.merge(device)
            db.commit()
        self._publish_device_control(agent_id, {"event": "registered", "state": "ready"})

    def _heartbeat(self, agent_id: str, message: Envelope) -> None:
        if message.device_id != AGENT_BY_ID[agent_id].device_id:
            return
        with self.session_factory() as db:
            device = db.get(DeviceStatus, agent_id)
            if not device:
                return
            state = str(message.payload.get("state", "ready"))
            if state not in {item.value for item in DeviceState}:
                device.state = DeviceState.ERROR.value
                device.last_error = f"invalid device state: {state[:64]}"
            else:
                device.state = state
                device.last_error = None
            device.last_seen_at = datetime.now(UTC)
            db.commit()

    def _generation_request(self, agent_id: str, message: Envelope) -> None:
        with self.session_factory() as db:
            session = self._validate_active_turn(db, agent_id, message)
            if not session:
                return
            history = [(turn.agent_id, turn.transcript) for turn in session.turns]
            response, backend = self.generator.generate(AGENT_BY_ID[agent_id], session.topic, history)
            self.issued_responses[message.turn_token or ""] = response
            if message.turn_token and session.active_turn_id:
                self.issued_turn_ids.setdefault(message.turn_token, session.active_turn_id)
            self._publish(
                topic_device(agent_id, "generation/response"),
                Envelope(
                    agent_id=agent_id,
                    device_id=AGENT_BY_ID[agent_id].device_id,
                    session_id=session.id,
                    turn_token=message.turn_token,
                    turn_id=message.turn_id,
                    event_type="generation.response",
                    sequence_number=len(history) + 1,
                    payload={"text": response, "generation_backend": backend},
                ),
            )

    def _turn_published(self, agent_id: str, message: Envelope) -> None:
        with self.session_factory() as db:
            session = self._validate_active_turn(db, agent_id, message)
            if not session:
                return
            token = message.turn_token or ""
            text = str(message.payload.get("text", "")).strip()
            if not text or self.issued_responses.get(token) != text:
                log.warning("Rejected unexpected/duplicate turn token %s", token)
                return
            next_sequence = len(session.turns) + 1
            agent = AGENT_BY_ID[agent_id]
            turn_id = self.issued_turn_ids.pop(token, session.active_turn_id)
            if not turn_id:
                log.warning("Rejected turn without an active turn identifier")
                return
            artifact = self.audio.create(session.id, turn_id, agent, text)
            turn = ExperimentTurn(
                id=turn_id,
                session_id=session.id,
                agent_id=agent_id,
                turn_token=token,
                sequence=next_sequence,
                round_number=session.completed_rounds + 1,
                transcript=text,
                voice=agent.voice,
                audio_file_path=str(artifact.path),
                acoustic_metadata={**artifact.features, "tts_backend": artifact.tts_backend},
                emotion_prediction=unavailable_emotion_prediction(
                    artifact.tts_backend, self.settings.emotion_model_checkpoint
                ),
            )
            db.add(turn)
            self.issued_responses.pop(token, None)
            session.active_turn_token = None
            session.active_turn_id = None
            session.active_sequence_number = None
            session.next_agent_index += 1
            if session.next_agent_index == len(TURN_ORDER):
                session.completed_rounds += 1
                session.next_agent_index = 0
            if session.completed_rounds >= session.requested_rounds:
                session.status = "completed"
            db.commit()
            db.refresh(session)
            self._publish_context(db, session)
            if session.status == "running":
                self._grant_expected_turn(db, session)
            else:
                self._publish(
                    f"lab/session/{session.id}/status",
                    Envelope(
                        session_id=session.id,
                        event_type="session.status",
                        payload={"status": session.status},
                    ),
                    retain=True,
                )

    def _validate_active_turn(
        self, db: Session, agent_id: str, message: Envelope
    ) -> ExperimentSession | None:
        if not message.session_id or not message.turn_token:
            return None
        session = db.get(ExperimentSession, message.session_id)
        if not session or session.status != "running":
            return None
        expected_agent = TURN_ORDER[session.next_agent_index]
        expected_turn_id = self.issued_turn_ids.get(message.turn_token) or session.active_turn_id
        if (
            expected_agent != agent_id
            or session.active_turn_token != message.turn_token
            or not expected_turn_id
            or message.turn_id != expected_turn_id
            or message.sequence_number != session.active_sequence_number
        ):
            log.warning("Rejected out-of-order message from %s", agent_id)
            return None
        return session

    def _grant_expected_turn(self, db: Session, session: ExperimentSession) -> None:
        agent_id = TURN_ORDER[session.next_agent_index]
        token = str(uuid4())
        turn_id = str(uuid4())
        session.active_turn_token = token
        session.active_turn_id = turn_id
        session.active_sequence_number = len(session.turns) + 1
        self.issued_turn_ids[token] = turn_id
        db.commit()
        self._publish(
            topic_device(agent_id, "turn/grant"),
            Envelope(
                agent_id=agent_id,
                device_id=AGENT_BY_ID[agent_id].device_id,
                session_id=session.id,
                turn_token=token,
                turn_id=turn_id,
                event_type="turn.grant",
                sequence_number=session.active_sequence_number,
                payload={
                    "sequence": len(
                        db.scalars(
                            select(ExperimentTurn.id).where(ExperimentTurn.session_id == session.id)
                        ).all()
                    )
                    + 1,
                    "round_number": session.completed_rounds + 1,
                },
            ),
        )

    def _publish_context(self, db: Session, session: ExperimentSession) -> None:
        turns = db.scalars(
            select(ExperimentTurn)
            .where(ExperimentTurn.session_id == session.id)
            .order_by(ExperimentTurn.sequence)
        ).all()
        history = [{"agent_id": turn.agent_id, "text": turn.transcript} for turn in turns]
        self._publish(
            topic_context(session.id),
            Envelope(
                session_id=session.id,
                event_type="session.context",
                payload={
                    "topic": session.topic,
                    "completed_rounds": session.completed_rounds,
                    "requested_rounds": session.requested_rounds,
                    "history": history,
                },
            ),
            retain=True,
        )

    def _publish_device_control(self, agent_id: str, payload: dict[str, str]) -> None:
        self._publish(
            topic_device(agent_id, "control"),
            Envelope(
                agent_id=agent_id,
                device_id=AGENT_BY_ID[agent_id].device_id,
                event_type="device.control",
                payload=payload,
            ),
        )

    def _publish(self, topic: str, message: Envelope, retain: bool = False) -> None:
        if not self.publisher:
            raise RuntimeError("MQTT publisher has not been attached")
        self.publisher.publish(topic, message, retain=retain)

    @staticmethod
    def _session_or_error(db: Session, session_id: str) -> ExperimentSession:
        session = db.get(ExperimentSession, session_id)
        if not session:
            raise ValueError("Experiment session was not found.")
        return session

    @staticmethod
    def _all_devices_online(db: Session) -> bool:
        records = {record.agent_id: record for record in db.scalars(select(DeviceStatus)).all()}
        return all(records.get(agent_id) and records[agent_id].state != "disconnected" for agent_id in AGENT_BY_ID)

