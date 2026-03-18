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


# ---------------------------------------------------------------------------
# Ingest progress broker — per-record_id SSE fan-out
# ---------------------------------------------------------------------------

class _IngestProgressBroker:
    """Fan-out SSE broker keyed by record_id, safe to call from async context.

    Maintains a last-event replay cache so late-connecting subscribers (e.g. the
    EMR page that navigates in after the upload response) receive the most recent
    progress state immediately upon subscribing.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = {}
        self._last_event: dict[str, dict[str, Any]] = {}  # last payload per record_id
        self._lock = asyncio.Lock()

    async def subscribe(self, record_id: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=50)
        async with self._lock:
            self._subscribers.setdefault(record_id, set()).add(queue)
            last = self._last_event.get(record_id)
        # Replay the most recent event so the frontend never sees a blank bar
        if last:
            try:
                replay = f"event: progress\ndata: {json.dumps(last, separators=(',', ':'))}\n\n"
                queue.put_nowait(replay)
            except asyncio.QueueFull:
                pass
        return queue

    async def unsubscribe(self, record_id: str, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            subs = self._subscribers.get(record_id)
            if subs:
                subs.discard(queue)
                if not subs:
                    del self._subscribers[record_id]

    async def publish(self, record_id: str, payload: dict[str, Any]) -> None:
        message = f"event: progress\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
        async with self._lock:
            self._last_event[record_id] = payload  # cache for late subscribers
            queues = list(self._subscribers.get(record_id, set()))
        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                continue


_ingest_broker = _IngestProgressBroker()


async def publish_ingest_progress(
    record_id: str,
    step: int,
    label: str,
    pct: int,
    status: str = "running",
) -> None:
    payload = {
        "record_id": record_id,
        "step": step,
        "label": label,
        "pct": pct,
        "status": status,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await _ingest_broker.publish(record_id, payload)


@router.get("/events/ingest-progress/{record_id}")
async def ingest_progress_events(record_id: str, request: Request):
    queue = await _ingest_broker.subscribe(record_id)

    async def event_generator():
        try:
            ready_payload = json.dumps(
                {"record_id": record_id, "status": "connected"}, separators=(",", ":")
            )
            yield f"event: ready\ndata: {ready_payload}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=20)
                    yield message
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            await _ingest_broker.unsubscribe(record_id, queue)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
