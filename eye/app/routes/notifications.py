import asyncio
import json
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, HTTPException, Response, WebSocket, WebSocketDisconnect, status
from redis.exceptions import RedisError

from app.notifications import notification_store
from app.schemas import SubAgentCallback, SubAgentNotification, WorkflowRunNotification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[SubAgentNotification | WorkflowRunNotification])
async def list_notifications() -> list[dict[str, Any]]:
    try:
        return await notification_store.list_notifications()
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Notification service unavailable") from exc


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def receive_sub_agent_result(payload: SubAgentCallback) -> Response:
    try:
        job = await notification_store.get_job(payload.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown or expired sub-agent job")
        if job["callback_token"] != payload.callback_token:
            raise HTTPException(status_code=401, detail="Invalid callback token")

        notification = await notification_store.complete_job(
            job=job,
            status=payload.status,
            response=payload.response,
            error=payload.error,
        )
        if notification is None:
            raise HTTPException(status_code=409, detail="Sub-agent job already completed")
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Notification service unavailable") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.websocket("/ws")
async def notification_socket(websocket: WebSocket) -> None:
    try:
        async with notification_store.client().pubsub() as pubsub:
            await pubsub.subscribe(notification_store.channel)
            await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            await websocket.accept()
            receive_task = asyncio.create_task(websocket.receive())
            try:
                while True:
                    message_task = asyncio.create_task(
                        pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=20,
                        )
                    )
                    done, _ = await asyncio.wait(
                        {receive_task, message_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if receive_task in done:
                        message_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await message_task
                        event = receive_task.result()
                        if event["type"] == "websocket.disconnect":
                            return
                        receive_task = asyncio.create_task(websocket.receive())
                        continue

                    message = message_task.result()
                    try:
                        if message is None:
                            await websocket.send_json({"type": "ping"})
                        else:
                            await websocket.send_json(
                                {
                                    "type": "notification",
                                    "data": json.loads(message["data"]),
                                }
                            )
                    except RuntimeError:
                        return
            finally:
                receive_task.cancel()
                with suppress(asyncio.CancelledError):
                    await receive_task
    except WebSocketDisconnect:
        return
    except RedisError:
        with suppress(RuntimeError):
            await websocket.close(code=1011, reason="Notification service unavailable")
