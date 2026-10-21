from app.agents.profiles import AGENT_PROFILES


def test_four_explicit_profiles_are_configured() -> None:
    assert [profile.id for profile in AGENT_PROFILES] == [
        "empathy",
        "critical",
        "optimistic",
        "moderator",
    ]
    assert [profile.voice for profile in AGENT_PROFILES] == ["nova", "onyx", "coral", "sage"]

