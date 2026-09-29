"""
WeatherGPT Live Call-Status WebSocket Router (SIH26068 — Demo/Observability Layer).

Exposes:
    GET /ws/call-status  — WebSocket endpoint; clients subscribe to receive
                           pipeline-stage events for in-progress calls.

Event shape (JSON):
    {
        "call_id":      str,          # UUID for the call, never the phone number
        "stage":        str,          # one of the STAGE_* constants below
        "phone_masked": str,          # last 4 digits only, e.g. "**6789"
        "language":     str | None,   # detected language code, e.g. "hi"
        "location":     str | None,   # resolved location name, never fabricated
        "location_tier": str | None,  # "spoken" | "profile" | "telecom" | None
        "timestamp":    str,          # ISO-8601 UTC
    }

SAFETY RULES (must never be violated):
  - Full phone numbers are NEVER broadcast. Only the last 4 digits are included.
  - Full transcript content is NEVER broadcast.
  - API credentials or auth tokens are NEVER sent over the socket.
  - broadcast_status() must NEVER raise, block, or retry-loop — it wraps every
    operation in a silent try/except so it cannot delay the SMS/advisory pipeline.
  - If no clients are connected, the broadcast is a no-op.

This module is purely observational: the call pipeline does NOT wait for
acknowledgement from WebSocket clients and does NOT depend on this module
for correctness. It is an optional demo/visibility layer only.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ws_demo"])

# Pipeline stage constants — kept as plain strings so they serialise cleanly.
STAGE_CALL_RECEIVED    = "call_received"
STAGE_LANG_DETECTED    = "language_detected"
STAGE_LOC_RESOLVED     = "location_resolved"
STAGE_ADVISORY_GEN     = "advisory_generated"
STAGE_SMS_DISPATCHED   = "sms_dispatched"
STAGE_LOC_PROMPT_SENT  = "location_prompt_sent"  # Tier-3 fail: asked caller for pin
STAGE_PIPELINE_FAILED  = "pipeline_failed"


class ConnectionManager:
    """
    Manages the set of active WebSocket connections.

    Thread/task safety:
        Mutations to _connections are guarded by asyncio — all operations run
        on the same event loop, so no explicit lock is needed.
    """

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("[WS] Client connected. Total: %d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("[WS] Client disconnected. Total: %d", len(self._connections))

    async def broadcast_status(self, event: dict) -> None:
        """
        Broadcast a JSON event to every connected WebSocket client.

        CRITICAL:
          - This method MUST NEVER raise an exception.
          - It MUST NEVER block (no retry loops, no sleep, no await on I/O
            beyond a single non-blocking send attempt per client).
          - Failed sends silently remove the dead client from the pool.
        """
        if not self._connections:
            return  # Fast-path: no clients

        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await asyncio.wait_for(ws.send_json(event), timeout=1.0)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[WS] Broadcast failed for a client (%s); removing.", exc)
                dead.append(ws)

        for ws in dead:
            self._connections.discard(ws)


# Module-level singleton imported by webhook.py
call_status_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# WebSocket route
# ---------------------------------------------------------------------------

@router.websocket("/ws/call-status")
async def ws_call_status(websocket: WebSocket) -> None:
    """
    Subscribe to the live call-status demo feed.

    Clients receive JSON events as calls progress through the advisory pipeline.
    This endpoint is read-only from the client perspective — no messages sent
    by the client are processed (they are silently ignored).

    Connection lifecycle:
        - Accept → add to pool → keep alive with a ping every 20 s.
        - On disconnect (client closes or network drop) → remove from pool.
    """
    await call_status_manager.connect(websocket)
    try:
        # Send a connection-confirmed handshake event immediately
        await websocket.send_json({
            "stage": "connected",
            "message": "WeatherGPT Live Call Activity Feed — demo/observability only.",
        })
        # Keep the connection alive; ignore any inbound messages from clients.
        while True:
            try:
                # Ping the client every 20 s so proxies/browsers don't drop idle sockets.
                await asyncio.sleep(20)
                await asyncio.wait_for(websocket.send_json({"stage": "ping"}), timeout=5.0)
            except asyncio.TimeoutError:
                logger.debug("[WS] Ping timed out; closing dead socket.")
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("[WS] Unexpected socket error: %s", exc)
    finally:
        call_status_manager.disconnect(websocket)
