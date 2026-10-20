from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cobrinha_server.bridge.godot_bridge import (
    godot_bridge,
)
from cobrinha_server.core.settings import (
    PROJECT_DIR,
    application_version,
)
from cobrinha_server.services import (
    game_launcher,
    live_watchdog,
    music_runtime,
)
from cobrinha_server.services.event_decision_worker import (
    status as event_decision_worker_status,
)
from cobrinha_server.services.speech_queue import (
    status as speech_queue_status,
)


router = APIRouter()


def _module_status() -> dict[str, bool]:
    base = (
        PROJECT_DIR
        / "src"
        / "cobrinha_server"
        / "services"
    )

    return {
        "audio_timeline": (
            base / "audio_timeline.py"
        ).is_file(),
        "game_launcher": (
            base / "game_launcher.py"
        ).is_file(),
    }


def _voice_stack_status() -> dict[str, bool]:
    result: dict[str, bool] = {}

    modules = {
        "piper": "piper",
        "onnxruntime": "onnxruntime",
    }

    for label, module_name in modules.items():
        result[label] = (
            importlib.util.find_spec(
                module_name
            )
            is not None
        )

    return result


def server_status() -> dict[str, Any]:
    music_state = music_runtime.status()
    watchdog = live_watchdog.status()
    queue_state = speech_queue_status()
    speech_active = bool(
        queue_state.get("active")
    )

    return {
        "ok": True,
        "service": "cobrinha-live-server",
        "version": application_version(),
        "time": time.time(),
        "godot": godot_bridge.status(),
        "game": game_launcher.status(),
        "vocal": {
            "mode": (
                "speech"
                if speech_active
                else "idle"
            ),
            "active": speech_active,
        },
        "music": {
            "background_tracks": int(
                music_state.get("track_count")
                or 0
            ),
            "runtime": music_state,
        },
        "event_decision_worker":
            event_decision_worker_status(),
        "speech_queue":
            queue_state,
        "watchdog":
            watchdog,
        "modules": _module_status(),
        "voice_stack": _voice_stack_status(),
        "live": {
            "running": bool(
                watchdog.get("active")
            ),
            "health": str(
                watchdog.get("status")
                or "idle"
            ),
        },
    }


@router.get(
    "/api/status",
    response_class=JSONResponse,
)
def api_status() -> JSONResponse:
    return JSONResponse(
        server_status()
    )


@router.post(
    "/api/godot/test-event",
    response_class=JSONResponse,
)
async def api_godot_test_event(
    request: Request,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    event_type = str(
        payload.get("type")
        or "integration_test"
    ).strip()

    if not event_type:
        event_type = "integration_test"

    message = {
        "type": event_type,
        "source": "server_panel_test",
        "time": time.time(),
        "payload": (
            payload.get("payload")
            if isinstance(
                payload.get("payload"),
                dict,
            )
            else {}
        ),
    }

    try:
        sent = await godot_bridge.send(
            message
        )
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "sent": False,
                "error": (
                    f"{type(exc).__name__}: {exc}"
                ),
            },
            status_code=500,
        )

    return JSONResponse(
        {
            "ok": True,
            "sent": bool(sent),
            "connected": bool(
                godot_bridge
                .status()
                .get("connected")
            ),
            "event": message,
        }
    )
