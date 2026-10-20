from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import WebSocket


class GodotBridge:
    def __init__(self) -> None:
        self._socket: WebSocket | None = None
        self._connected_at: float = 0.0
        self._last_message_at: float = 0.0
        self._last_payload: dict[str, Any] = {}
        self._last_by_type: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        socket: WebSocket,
    ) -> None:
        await socket.accept()

        async with self._lock:
            self._socket = socket
            self._connected_at = time.time()
            self._last_message_at = time.time()
            self._last_payload = {}
            self._last_by_type = {}

    async def disconnect(
        self,
        socket: WebSocket,
    ) -> None:
        async with self._lock:
            if self._socket is socket:
                self._socket = None

    async def remember(
        self,
        payload: dict[str, Any],
    ) -> None:
        received_at = time.time()
        stored_payload = dict(payload)
        stored_payload["_received_at"] = received_at

        async with self._lock:
            self._last_message_at = received_at
            self._last_payload = dict(stored_payload)

            message_type = str(
                payload.get("type") or ""
            ).strip()

            if message_type:
                self._last_by_type[message_type] = dict(
                    stored_payload
                )

    async def send(
        self,
        payload: dict[str, Any],
    ) -> bool:
        async with self._lock:
            socket = self._socket

        if socket is None:
            return False

        await socket.send_json(payload)
        return True

    def status(self) -> dict[str, Any]:
        return {
            "connected": self._socket is not None,
            "connected_at": self._connected_at,
            "last_message_at": self._last_message_at,
            "last_payload": dict(
                self._last_payload
            ),
            "last_by_type": {
                key: dict(value)
                for key, value in self._last_by_type.items()
            },
        }


godot_bridge = GodotBridge()
