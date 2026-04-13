from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["events"])

_INGEST_PROGRESS_CACHE_DIR = Path("/tmp/emr_ingest_progress")
_INGEST_PROGRESS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _progress_cache_path(record_id: str) -> Path:
    safe = "".join(ch for ch in record_id if ch.isalnum() or ch in ("-", "_"))
    return _INGEST_PROGRESS_CACHE_DIR / f"{safe}.json"


def _write_progress_cache(record_id: str, payload: dict[str, Any]) -> None:
    path = _progress_cache_path(record_id)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)


def _read_progress_cache(record_id: str) -> dict[str, Any] | None:
    path = _progress_cache_path(record_id)
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_progress_ts(payload: dict[str, Any] | None) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    raw = str(payload.get("ts") or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _pick_newer_progress(
    memory_payload: dict[str, Any] | None,
    disk_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(memory_payload, dict):
        return dict(disk_payload) if isinstance(disk_payload, dict) else None
    if not isinstance(disk_payload, dict):
        return dict(memory_payload)

    memory_ts = _parse_progress_ts(memory_payload)
    disk_ts = _parse_progress_ts(disk_payload)
    if memory_ts and disk_ts:
        return dict(disk_payload if disk_ts > memory_ts else memory_payload)
    if disk_ts and not memory_ts:
        return dict(disk_payload)
    if memory_ts and not disk_ts:
        return dict(memory_payload)

    # If timestamps are missing/corrupt, prefer the payload with higher step/pct.
    memory_step = int(memory_payload.get("step") or 0)
    disk_step = int(disk_payload.get("step") or 0)
    if disk_step != memory_step:
        return dict(disk_payload if disk_step > memory_step else memory_payload)
    memory_pct = int(memory_payload.get("pct") or 0)
    disk_pct = int(disk_payload.get("pct") or 0)
    return dict(disk_payload if disk_pct > memory_pct else memory_payload)


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
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": keepalive\n\n"
                except asyncio.CancelledError:
                    break
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
            memory_last = self._last_event.get(record_id)

        disk_last = _read_progress_cache(record_id)
        last = _pick_newer_progress(memory_last, disk_last)

        if isinstance(last, dict):
            async with self._lock:
                current = self._last_event.get(record_id)
                merged = _pick_newer_progress(current, last)
                if isinstance(merged, dict):
                    self._last_event[record_id] = merged

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
        _write_progress_cache(record_id, payload)
        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                continue

    async def latest(self, record_id: str) -> dict[str, Any] | None:
        async with self._lock:
            memory_cached = self._last_event.get(record_id)

        disk_cached = _read_progress_cache(record_id)
        latest = _pick_newer_progress(memory_cached, disk_cached)
        if isinstance(latest, dict):
            async with self._lock:
                self._last_event[record_id] = latest
        return latest


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


@router.get("/events/ingest-progress/{record_id}/latest")
async def ingest_progress_latest(record_id: str):
    latest = await _ingest_broker.latest(record_id)
    if latest:
        return latest
    return {
        "record_id": record_id,
        "step": 1,
        "label": "等待后台分析进度...",
        "pct": 0,
        "status": "pending",
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/events/ingest-progress/{record_id}")
async def ingest_progress_events(record_id: str, request: Request):
    queue = await _ingest_broker.subscribe(record_id)

    async def event_generator():
        last_sent_ts = ""

        def _payload_ts(payload: dict[str, Any]) -> str:
            return str(payload.get("ts") or "")

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
                    try:
                        parts = str(message).split("data:", 1)
                        if len(parts) == 2:
                            payload = json.loads(parts[1].strip())
                            if isinstance(payload, dict):
                                ts = _payload_ts(payload)
                                if ts:
                                    last_sent_ts = ts
                    except Exception:
                        pass
                    yield message
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    latest = await _ingest_broker.latest(record_id)
                    if isinstance(latest, dict):
                        ts = _payload_ts(latest)
                        if ts and ts != last_sent_ts:
                            last_sent_ts = ts
                            replay = f"event: progress\ndata: {json.dumps(latest, separators=(',', ':'))}\n\n"
                            yield replay
                            continue
                    yield ": keepalive\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            await _ingest_broker.unsubscribe(record_id, queue)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
