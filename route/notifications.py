"""WebSocket notifications for real-time EMR/diagnostic analysis updates."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any, Deque, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

router = APIRouter(tags=["notifications"])
logger = logging.getLogger(__name__)

# Global event queue for notifications (thread-safe)
_notification_queue: Deque[dict[str, Any]] = deque(maxlen=100)


class EmrGeneratedNotification(BaseModel):
    """Schema for EMR generated notification from backend."""
    record_id: str
    emr_id: str
    patient_id: str


class ConnectionManager:
    """Manage WebSocket connections and broadcast notifications."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("WebSocket client connected. Total connections: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        """Unregister a disconnected client."""
        self.active_connections.discard(websocket)
        logger.info("WebSocket client disconnected. Total connections: %d", len(self.active_connections))

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as exc:
                logger.warning("Failed to send message to client: %s", exc)
                disconnected.add(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


_manager = ConnectionManager()


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """WebSocket endpoint for real-time notifications."""
    await _manager.connect(websocket)
    try:
        while True:
            # Keep connection alive by receiving (but we don't process client messages)
            data = await websocket.receive_text()
            # Optionally log or process ping/pong messages
            if data.lower() in ("ping", "pong"):
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        _manager.disconnect(websocket)


def add_notification_event(notification_type: str, **kwargs):
    """Add a notification event to the queue (can be called from any thread/async context)."""
    message = {
        "type": notification_type,
        **kwargs,
    }
    _notification_queue.append(message)
    logger.debug("Added notification event to queue: type=%s", notification_type)


async def dispatch_queued_notifications():
    """Dispatch all queued notifications to connected WebSocket clients."""
    while _notification_queue:
        message = _notification_queue.popleft()
        await _manager.broadcast(message)
        logger.info("Dispatched queued notification: type=%s", message.get("type"))


@router.get("/api/notifications/dispatch")
async def dispatch_notifications_endpoint():
    """Endpoint to dispatch queued notifications. Call this periodically to flush queue."""
    count = len(_notification_queue)
    await dispatch_queued_notifications()
    return {
        "dispatched": count,
        "remaining": len(_notification_queue),
    }


@router.post("/ws-notify/emr-generated")
async def notify_emr_generated_endpoint(payload: EmrGeneratedNotification):
    """Endpoint for ingestion service to notify of EMR generation completion."""
    record_id = payload.record_id
    emr_id = payload.emr_id
    patient_id = payload.patient_id
    
    notification = {
        "type": "emr_generated",
        "record_id": record_id,
        "emr_id": emr_id,
        "patient_id": patient_id,
        "message": "诊断分析报告已生成，请刷新查看最新结果",
    }
    
    # Add to queue and broadcast immediately
    add_notification_event(
        "emr_generated",
        record_id=record_id,
        emr_id=emr_id,
        patient_id=patient_id,
        message="诊断分析报告已生成，请刷新查看最新结果",
    )
    await _manager.broadcast(notification)
    
    logger.info(
        "received emr_generated notification record_id=%s emr_id=%s patient_id=%s",
        record_id,
        emr_id,
        patient_id,
    )
    
    return {
        "status": "received",
        "emr_id": emr_id,
    }


async def notify_emr_generated(record_id: str, emr_id: str, patient_id: str):
    """Queue a notification that a new EMR has been generated."""
    notification = {
        "type": "emr_generated",
        "record_id": record_id,
        "emr_id": emr_id,
        "patient_id": patient_id,
        "message": "诊断分析报告已生成，请刷新查看最新结果",
    }
    add_notification_event(
        "emr_generated",
        record_id=record_id,
        emr_id=emr_id,
        patient_id=patient_id,
        message="诊断分析报告已生成，请刷新查看最新结果",
    )
    logger.info(
        "queued emr_generated notification record_id=%s emr_id=%s patient_id=%s",
        record_id,
        emr_id,
        patient_id,
    )
    # Also immediately broadcast to any connected clients
    await _manager.broadcast(notification)


__all__ = ["router", "notify_emr_generated", "add_notification_event", "dispatch_queued_notifications"]
