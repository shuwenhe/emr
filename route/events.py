from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["events"])


class _PatientEventBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        message = f"event: {event_name}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
        async with self._lock:
            queues = list(self._subscribers)

        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Drop stale events for slow subscribers to keep stream responsive.
                continue


_patient_broker = _PatientEventBroker()


async def publish_patient_event(event_name: str, patient_id: str) -> None:
    payload = {
        "patient_id": patient_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await _patient_broker.publish(event_name, payload)


@router.get("/events/patients")
async def patient_events(request: Request):
    queue = await _patient_broker.subscribe()

    async def event_generator():
        try:
            ready_payload = json.dumps({"status": "connected"}, separators=(",", ":"))
            yield f"event: ready\ndata: {ready_payload}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield message
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            await _patient_broker.unsubscribe(queue)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
