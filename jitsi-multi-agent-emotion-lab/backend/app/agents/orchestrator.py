from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.client import ChatGenerator
from app.agents.profiles import AGENT_PROFILES
from app.audio.analysis import AcousticAnalyzer
from app.audio.synthesis import SpeechSynthesizer
from app.config import Settings
from app.emotion.classifier import AudioEmotionClassifier
from app.models import DiscussionSession, DiscussionTurn


class DiscussionOrchestrator:
    """Bounded, sequential four-agent turn-taking; never self-spawns agent loops."""

    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]):
        self.settings = settings
        self.session_factory = session_factory
        self.chat = ChatGenerator(settings)
        self.speech = SpeechSynthesizer(settings)
        self.acoustics = AcousticAnalyzer()
        self.emotion = AudioEmotionClassifier(settings)

    async def run(self, session_id: str) -> None:
        try:
            self._set_status(session_id, "running")
            while True:
                state = self._get_session(session_id)
                if state.status in {"paused", "stopped", "completed"}:
                    return
                if state.completed_rounds >= state.requested_rounds:
                    self._set_status(session_id, "completed")
                    return
                round_number = state.completed_rounds + 1
                for profile in AGENT_PROFILES:
                    if self._get_session(session_id).status in {"paused", "stopped"}:
                        return
                    history = self._history(session_id)
                    transcript, text_backend = await self.chat.generate(profile, state.topic, history)
                    turn_id = str(uuid4())
                    synthesis = await self.speech.synthesize(session_id, turn_id, profile, transcript)
                    features = await asyncio.to_thread(self.acoustics.extract, synthesis.path)
                    prediction = self.emotion.predict(features)
                    self._save_agent_turn(
                        session_id=session_id,
                        turn_id=turn_id,
                        round_number=round_number,
                        profile_id=profile.id,
                        transcript=transcript,
                        voice=profile.voice,
                        intended_style=profile.speaking_style,
                        audio_path=str(synthesis.path),
                        generation_backend=f"{text_backend}+{synthesis.backend}",
                        feature_version=features["version"],
                        features=features,
                        prediction=prediction,
                    )
                self._finish_round(session_id, round_number)
        except Exception:
            self._set_status(session_id, "failed")

    def _get_session(self, session_id: str) -> DiscussionSession:
        with self.session_factory() as db:
            record = db.get(DiscussionSession, session_id)
            if not record:
                raise ValueError(f"Unknown session: {session_id}")
            db.expunge(record)
            return record

    def _history(self, session_id: str) -> list[tuple[str, str]]:
        with self.session_factory() as db:
            records = db.scalars(
                select(DiscussionTurn)
                .where(DiscussionTurn.session_id == session_id)
                .order_by(DiscussionTurn.sequence)
            ).all()
            return [(turn.agent_id or "user", turn.transcript) for turn in records]

    def _set_status(self, session_id: str, status: str) -> None:
        with self.session_factory() as db:
            record = db.get(DiscussionSession, session_id)
            if record and not (record.status == "stopped" and status == "running"):
                record.status = status
                db.commit()

    def _save_agent_turn(self, **values: object) -> None:
        with self.session_factory() as db:
            count = db.scalar(
                select(DiscussionTurn).where(DiscussionTurn.session_id == values["session_id"])
            )
            # sequence only needs monotonicity inside one sequential orchestrator task.
            sequence = len(
                db.scalars(
                    select(DiscussionTurn.id).where(DiscussionTurn.session_id == values["session_id"])
                ).all()
            ) + 1
            del count
            db.add(
                DiscussionTurn(
                    id=values["turn_id"],
                    session_id=values["session_id"],
                    sequence=sequence,
                    round_number=values["round_number"],
                    speaker_type="agent",
                    agent_id=values["profile_id"],
                    transcript=values["transcript"],
                    voice=values["voice"],
                    intended_style=values["intended_style"],
                    audio_file_path=values["audio_path"],
                    generation_backend=values["generation_backend"],
                    feature_extraction_version=values["feature_version"],
                    features=values["features"],
                    emotion_prediction=values["prediction"],
                )
            )
            db.commit()

    def _finish_round(self, session_id: str, round_number: int) -> None:
        with self.session_factory() as db:
            record = db.get(DiscussionSession, session_id)
            if record and record.status == "running":
                record.completed_rounds = round_number
                if round_number >= record.requested_rounds:
                    record.status = "completed"
                db.commit()

