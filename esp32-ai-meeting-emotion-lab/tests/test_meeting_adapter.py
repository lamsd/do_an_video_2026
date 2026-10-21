from pathlib import Path

from app.identities import AGENT_BY_ID
from app.meeting.adapter import InMemoryMeetingAdapter, participant_for


def test_virtual_participant_is_explicitly_labeled_ai_bot() -> None:
    participant = participant_for(AGENT_BY_ID["empathy"], Path("/tmp/empathy.wav"))
    assert participant.display_name == "AI Bot · AI-Empathy-01"
    assert participant.voice == "nova"


def test_in_memory_adapter_keeps_four_identity_contract_testable() -> None:
    adapter = InMemoryMeetingAdapter()
    adapter.connect()
    participant = participant_for(AGENT_BY_ID["empathy"], Path("/tmp/empathy.wav"))
    adapter.join_room("nghiem-thu", participant)
    adapter.subscribe_audio("empathy")
    adapter.publish_audio("empathy", participant.audio_path)
    assert adapter.get_connection_state() == "joined"
    assert adapter.list_participants() == [participant]
    assert adapter.published_audio == [("empathy", Path("/tmp/empathy.wav"))]

