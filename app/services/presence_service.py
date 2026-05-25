from app.repositories import contact_repo, user_repo
from app.services.pubsub import get_redis, publish_message


PRESENCE_TTL_SECONDS = 45


def _presence_session_key(user_id: int, session_id: str) -> str:
    return f"presence:{user_id}:session:{session_id}"


def _presence_sessions_key(user_id: int) -> str:
    return f"presence:{user_id}:sessions"


async def _active_sessions(redis, user_id: int) -> set[str]:
    members = list(await redis.smembers(_presence_sessions_key(user_id)))
    if not members:
        return set()

    pipeline = redis.pipeline()
    for session_id in members:
        pipeline.exists(_presence_session_key(user_id, session_id))
    exists_results = await pipeline.execute()

    active: set[str] = set()
    stale: list[str] = []
    for session_id, exists in zip(members, exists_results):
        if exists:
            active.add(session_id)
        else:
            stale.append(session_id)

    if stale:
        await redis.srem(_presence_sessions_key(user_id), *stale)
    if not active:
        await redis.delete(_presence_sessions_key(user_id))
    return active


async def mark_online(user_id: int, session_id: str) -> bool:
    redis = get_redis()
    try:
        was_online = bool(await _active_sessions(redis, user_id))
        await redis.set(_presence_session_key(user_id, session_id), "online", ex=PRESENCE_TTL_SECONDS)
        await redis.sadd(_presence_sessions_key(user_id), session_id)
        return not was_online
    finally:
        await redis.aclose()


async def mark_offline(user_id: int, session_id: str) -> bool:
    redis = get_redis()
    try:
        was_online = bool(await _active_sessions(redis, user_id))
        await redis.delete(_presence_session_key(user_id, session_id))
        await redis.srem(_presence_sessions_key(user_id), session_id)
        still_online = bool(await _active_sessions(redis, user_id))
        return was_online and not still_online
    finally:
        await redis.aclose()


async def is_online(user_id: int) -> bool:
    redis = get_redis()
    try:
        return bool(await _active_sessions(redis, user_id))
    finally:
        await redis.aclose()


async def heartbeat_and_broadcast(db, user_id: int, session_id: str):
    became_online = await mark_online(user_id, session_id)
    if became_online:
        await broadcast_presence_change(db, user_id, True)
    return {"status": "ok", "ttl_seconds": PRESENCE_TTL_SECONDS}


async def disconnect_and_broadcast(db, user_id: int, session_id: str):
    became_offline = await mark_offline(user_id, session_id)
    if became_offline:
        await broadcast_presence_change(db, user_id, False)


async def broadcast_presence_change(db, user_id: int, is_online_now: bool):
    actor = user_repo.get_user_by_id(db, user_id)
    if not actor:
        return
    payload = {
        "type": "presence_changed",
        "user_id": user_id,
        "username": actor.username,
        "is_online": is_online_now,
    }
    for contact_id in contact_repo.get_contact_ids(db, user_id):
        await publish_message(contact_id, payload)


async def get_contacts_presence(db, user_id: int):
    contact_ids = contact_repo.get_contact_ids(db, user_id)
    if not contact_ids:
        return []

    redis = get_redis()
    rows = []
    for contact_id in contact_ids:
        user = user_repo.get_user_by_id(db, contact_id)
        if not user:
            continue
        rows.append(
            {
                "user_id": contact_id,
                "username": user.username,
                "is_online": bool(await _active_sessions(redis, contact_id)),
            }
        )
    await redis.aclose()
    return rows
