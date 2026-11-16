import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

# Importing the worker initializes the application database module. Keep this
# unit test independent of a local settings.env file.
os.environ.setdefault("VEXA_API_BASE", "http://vexa.test")
os.environ.setdefault("POSTGRES_PASSWORD", "test-password")

from app.workers import sentiment


class FakeRedis:
    def __init__(self, claimed_entries=None):
        self.claimed_entries = claimed_entries or []
        self.acks = []
        self.claim_arguments = None

    async def xack(self, *arguments):
        self.acks.append(arguments)

    async def xautoclaim(self, *arguments, **kwargs):
        self.claim_arguments = (arguments, kwargs)
        return ["0-0", self.claimed_entries, []]


@pytest.mark.asyncio
async def test_reclaimed_pending_entry_is_processed_then_acknowledged(monkeypatch):
    run_id = uuid4()
    redis = FakeRedis([("42-0", {"run_id": str(run_id)})])
    processed = []
    monkeypatch.setattr(
        sentiment,
        "get_settings",
        lambda: SimpleNamespace(
            analysis_stream="jobs",
            analysis_consumer_group="workers",
            analysis_reclaim_idle_seconds=60,
        ),
    )

    async def fake_process(identifier, classifier):
        processed.append((identifier, classifier))

    monkeypatch.setattr(sentiment, "process", fake_process)

    assert await sentiment.reclaim_pending_entries(redis, "classifier", "replacement") == 1
    assert processed == [(run_id, "classifier")]
    assert redis.acks == [("jobs", "workers", "42-0")]
    assert redis.claim_arguments == (("jobs", "workers", "replacement"), {
        "min_idle_time": 60_000,
        "start_id": "0-0",
        "count": 20,
    })


@pytest.mark.asyncio
async def test_transient_entry_failure_stays_pending_for_the_next_worker(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(
        sentiment,
        "get_settings",
        lambda: SimpleNamespace(analysis_stream="jobs", analysis_consumer_group="workers"),
    )

    async def interrupted_process(_identifier, _classifier):
        raise OSError("database connection dropped")

    monkeypatch.setattr(sentiment, "process", interrupted_process)

    assert await sentiment.process_stream_entries(redis, [("7-0", {"run_id": str(uuid4())})], object()) == 0
    assert redis.acks == []


@pytest.mark.asyncio
async def test_malformed_entry_is_acknowledged_to_avoid_a_poison_message_loop(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(
        sentiment,
        "get_settings",
        lambda: SimpleNamespace(analysis_stream="jobs", analysis_consumer_group="workers"),
    )

    assert await sentiment.process_stream_entries(redis, [("bad-0", {})], object()) == 0
    assert redis.acks == [("jobs", "workers", "bad-0")]
