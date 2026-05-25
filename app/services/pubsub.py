import json

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.config import settings


USER_EVENT_STREAM_MAXLEN = 1000
USER_EVENT_BLOCK_MS = 30000


def get_redis():
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _event_stream_key(user_id: int) -> str:
    return f"user:{user_id}:events"


async def publish_message(user_id: int, payload: dict):
    r = get_redis()
    try:
        await r.xadd(
            _event_stream_key(user_id),
            {"payload": json.dumps(payload)},
            maxlen=USER_EVENT_STREAM_MAXLEN,
            approximate=True,
        )
    except (OSError, RedisError):
        if settings.DEPLOY_ENV in {"local", "test"}:
            return
        raise
    finally:
        await r.aclose()


async def subscribe_to_user(user_id: int, *, last_event_id: str = "$"):
    return {
        "user_id": user_id,
        "last_event_id": last_event_id,
        "redis": get_redis(),
    }


async def read_user_messages(subscription: dict, *, block_ms: int = USER_EVENT_BLOCK_MS) -> list[dict]:
    entries = await subscription["redis"].xread(
        {_event_stream_key(subscription["user_id"]): subscription["last_event_id"]},
        count=100,
        block=block_ms,
    )
    if not entries:
        return []

    payloads: list[dict] = []
    for _, stream_entries in entries:
        for event_id, values in stream_entries:
            subscription["last_event_id"] = event_id
            raw_payload = values.get("payload")
            if not raw_payload:
                continue
            try:
                payloads.append(json.loads(raw_payload))
            except json.JSONDecodeError:
                continue
    return payloads


async def unsubscribe_from_user(subscription: dict):
    await subscription["redis"].aclose()
