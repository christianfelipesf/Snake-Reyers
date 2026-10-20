from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cobrinha_server.bridge.godot_bridge import (
    godot_bridge,
    preview_bridge,
)
from cobrinha_server.services.preview_renderer import (
    preview_status,
    terrain_editor_status,
)
from cobrinha_server.services.output_state import (
    status as output_status,
)
from cobrinha_server.services import (
    live_watchdog,
    music_runtime,
    song_runtime,
)
from cobrinha_server.services.event_decision_worker import (
    status as event_decision_worker_status,
)
from cobrinha_server.services.speech_queue import (
    status as speech_queue_status,
)
from cobrinha_server.core.settings import (
    ASSETS_DIR,
    PROJECT_DIR,
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
        "audio_routing": (
            base / "audio_routing.py"
        ).is_file(),
        "transmission": (
            base / "transmission.py"
        ).is_file(),
    }


def _voice_stack_status() -> dict[str, bool]:
    result: dict[str, bool] = {}

    modules = {
        "demucs": "demucs",
        "torch": "torch",
        "torchaudio": "torchaudio",
        "tts": "TTS",
        "transformers": "transformers",
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
    music_dir = (
        ASSETS_DIR
        / "music"
        / "background"
    )
    songs_dir = (
        ASSETS_DIR
        / "songs"
    )

    music_count = len(
        [
            path
            for path in music_dir.glob("*")
            if path.is_file()
            and not path.name.startswith(".")
        ]
    )

    song_state = song_runtime.status()
    processed_songs = (
        song_state.get("songs")
        if isinstance(
            song_state.get("songs"),
            list,
        )
        else []
    )
    processing = (
        song_state.get("processing")
        if isinstance(
            song_state.get("processing"),
            dict,
        )
        else {}
    )
    active_song = (
        song_state.get("active")
        if isinstance(
            song_state.get("active"),
            dict,
        )
        else {}
    )
    song_count = len(processed_songs)
    watchdog = live_watchdog.status()
    output = output_status()

    return {
        "ok": True,
        "service": "cobrinha-live-server",
        "version": "0.1.0",
        "time": time.time(),
        "godot": godot_bridge.status(),
        "preview": {
            "process": preview_status(),
            "bridge": preview_bridge.status(),
        },
        "terrain_editor": {
            "process": terrain_editor_status(),
        },
        "vocal": {
            "mode": (
                "processing"
                if processing.get("active")
                else (
                    "singing"
                    if active_song.get("playing")
                    else "idle"
                )
            ),
            "active": bool(
                processing.get("active")
                or active_song.get("playing")
            ),
            "song_runtime": song_state,
        },
        "music": {
            "background_tracks": music_count,
            "songs": song_count,
            "runtime":
                music_runtime.status(),
        },
        "event_decision_worker":
            event_decision_worker_status(),
        "speech_queue":
            speech_queue_status(),
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
        "transmission":
            output,
        "output":
            output,
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
