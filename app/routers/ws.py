import asyncio
import contextlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter,WebSocket,WebSocketDisconnect,Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.crypto import decode_access_token
from app.models import Device
from app.services import manager,read_user_messages,subscribe_to_user,unsubscribe_from_user
from app.services import presence_service

router = APIRouter(tags=["websocket"])


def _extract_bearer_token(websocket: WebSocket) -> str | None:
    auth_header = websocket.headers.get("authorization")
    if not auth_header:
        return None
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    user_id:int,
    websocket: WebSocket,
    db: Session = Depends(get_db)
):
    token = _extract_bearer_token(websocket)
    if not token:
        await websocket.close(code=1008)
        return
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=1008)
        return
    if payload.get("type") != "access":
        await websocket.close(code=1008)
        return
    try:
        token_user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        await websocket.close(code=1008)
        return
    if token_user_id!=user_id:
        await websocket.close(code=1008)
        return
    device_id = payload.get("device_id")
    if device_id:
        device = (
            db.query(Device)
            .filter(Device.id == device_id, Device.user_id == user_id)
            .first()
        )
        if device is None or device.revoked_at is not None:
            await websocket.close(code=1008)
            return
    session_id = f"ws:{uuid.uuid4().hex}"
    subscription = None
    await manager.connect(user_id,websocket)
    try:
        await presence_service.heartbeat_and_broadcast(db, user_id, session_id)
        subscription = await subscribe_to_user(user_id)
        await websocket.send_json(
            {
                "type": "sync_hint",
                "reason": "websocket_connected",
                "refresh_presence": True,
            }
        )

        async def client_listener():
            try:
                while True:
                    text = await websocket.receive_text()
                    if text == "ping":
                        await websocket.send_text("pong")
                        await presence_service.heartbeat_and_broadcast(db, user_id, session_id)
            except WebSocketDisconnect:
                pass

        async def redis_listener():
            try:
                while True:
                    for payload in await read_user_messages(subscription):
                        await websocket.send_json(payload)
            except Exception:
                pass

        async def token_expiry_listener():
            exp_value = payload.get("exp")
            if not exp_value:
                return
            try:
                exp_ts = float(exp_value)
            except (TypeError, ValueError):
                return
            delay_seconds = max(exp_ts - datetime.now(timezone.utc).timestamp(), 0.0)
            await asyncio.sleep(delay_seconds)
            with contextlib.suppress(Exception):
                await websocket.close(code=4001, reason="token_expired")

        redis_task = asyncio.create_task(client_listener())
        ws_task = asyncio.create_task(redis_listener())
        expiry_task = asyncio.create_task(token_expiry_listener())

        try:
            await asyncio.wait(
                [redis_task,ws_task, expiry_task],
                return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for task in (redis_task, ws_task, expiry_task):
                task.cancel()
            for task in (redis_task, ws_task, expiry_task):
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
    finally:
        manager.disconnect(user_id, websocket)
        if subscription is not None:
            await unsubscribe_from_user(subscription)
        with contextlib.suppress(Exception):
            await presence_service.disconnect_and_broadcast(db, user_id, session_id)
