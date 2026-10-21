from pathlib import Path

from app.config import Settings
from app.coordinator import TurnCoordinator
from app.db import Base
from app.identities import AGENTS, TURN_ORDER
from app.models import DeviceStatus, ExperimentSession
from app.protocol import Envelope, topic_device
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class CapturingPublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, Envelope, bool]] = []

    def publish(self, topic: str, envelope: Envelope, retain: bool = False) -> None:
        self.events.append((topic, envelope, retain))


def _session_factory(database_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        for agent in AGENTS:
            db.add(DeviceStatus(agent_id=agent.agent_id, device_id=agent.device_id, state="ready"))
        db.commit()
    return factory


def test_coordinator_accepts_exactly_one_ordered_discussion_round(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path / "test.db")
    coordinator = TurnCoordinator(Settings(media_root=tmp_path / "media"), factory)
    publisher = CapturingPublisher()
    coordinator.attach_publisher(publisher)  # type: ignore[arg-type]

    created = coordinator.start("Consent-centered meeting assistants", rounds=1)
    for expected_agent in TURN_ORDER:
        grant_topic, grant, _ = next(
            event
            for event in reversed(publisher.events)
            if event[0] == topic_device(expected_agent, "turn/grant")
        )
        assert grant_topic.endswith("turn/grant")
        coordinator.handle_message(
            topic_device(expected_agent, "generation/request"),
            Envelope(
                agent_id=expected_agent,
                device_id={agent.agent_id: agent.device_id for agent in AGENTS}[expected_agent],
                session_id=created.id,
                turn_token=grant.turn_token,
                turn_id=grant.turn_id,
                sequence_number=grant.sequence_number,
            ),
        )
        _, generated, _ = next(
            event
            for event in reversed(publisher.events)
            if event[0] == topic_device(expected_agent, "generation/response")
        )
        coordinator.handle_message(
            topic_device(expected_agent, "turn/published"),
            Envelope(
                agent_id=expected_agent,
                device_id={agent.agent_id: agent.device_id for agent in AGENTS}[expected_agent],
                session_id=created.id,
                turn_token=grant.turn_token,
                turn_id=grant.turn_id,
                sequence_number=grant.sequence_number,
                payload={"text": generated.payload["text"]},
            ),
        )

    with factory() as db:
        saved = db.get(ExperimentSession, created.id)
        assert saved is not None
        assert saved.status == "completed"
        assert [turn.agent_id for turn in saved.turns] == list(TURN_ORDER)
        assert all(turn.emotion_prediction["status"] == "unavailable" for turn in saved.turns)

    # Replaying the final broker event cannot create an additional persisted turn.
    final_agent = TURN_ORDER[-1]
    coordinator.handle_message(
        topic_device(final_agent, "turn/published"),
        Envelope(
            agent_id=final_agent,
            device_id={agent.agent_id: agent.device_id for agent in AGENTS}[final_agent],
            session_id=created.id,
            turn_token=grant.turn_token,
            turn_id=grant.turn_id,
            sequence_number=grant.sequence_number,
            payload={"text": generated.payload["text"]},
        ),
    )
    with factory() as db:
        saved = db.get(ExperimentSession, created.id)
        assert saved is not None
        assert len(saved.turns) == len(TURN_ORDER)


def test_pause_invalidates_active_capability_and_resume_issues_a_new_one(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path / "pause.db")
    coordinator = TurnCoordinator(Settings(media_root=tmp_path / "media"), factory)
    publisher = CapturingPublisher()
    coordinator.attach_publisher(publisher)  # type: ignore[arg-type]
    session = coordinator.start("Kiểm thử pause an toàn", rounds=1)

    _, first_grant, _ = next(event for event in publisher.events if event[0].endswith("turn/grant"))
    coordinator.pause(session.id)
    first_agent = TURN_ORDER[0]
    coordinator.handle_message(
        topic_device(first_agent, "generation/request"),
        Envelope(
            agent_id=first_agent,
            device_id={agent.agent_id: agent.device_id for agent in AGENTS}[first_agent],
            session_id=session.id,
            turn_token=first_grant.turn_token,
            turn_id=first_grant.turn_id,
            sequence_number=first_grant.sequence_number,
        ),
    )
    assert not any(topic.endswith("generation/response") for topic, _, _ in publisher.events)

    coordinator.resume(session.id)
    _, resumed_grant, _ = next(
        event
        for event in reversed(publisher.events)
        if event[0] == topic_device(first_agent, "turn/grant")
    )
    assert resumed_grant.turn_token != first_grant.turn_token
    assert resumed_grant.turn_id != first_grant.turn_id
    assert resumed_grant.sequence_number == 1

