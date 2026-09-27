from uuid import UUID

from redis.asyncio import Redis

from .config import get_settings


async def enqueue_analysis(run_id: UUID) -> None:
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.xadd(settings.analysis_stream, {"run_id": str(run_id)})
    finally:
        await client.aclose()


def decode_run_id(fields: dict[str, str | bytes]) -> str:
    value = fields.get("run_id")
    if isinstance(value, bytes):
        return value.decode()
    if not isinstance(value, str):
        raise TypeError("analysis job is missing run_id")
    return value
