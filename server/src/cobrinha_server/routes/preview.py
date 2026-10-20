from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import JSONResponse

from cobrinha_server.bridge.godot_bridge import (
    preview_bridge,
)
from cobrinha_server.services.preview_renderer import (
    preview_status,
    start_terrain_editor,
    start_preview,
    terrain_editor_status,
)
from cobrinha_server.services.preview_social_dispatcher import (
    status as preview_social_dispatcher_status,
)
from cobrinha_server.services.avatar_cache import (
    cache_profile_avatar,
)
from cobrinha_server.services.social_events import (
    normalize_social_user,
    spectator_user_message,
)
from cobrinha_server.services.tts_service import (
    prepare_tts_input,
    synthesize_for_job,
)


router = APIRouter()


@router.get(
    "/api/preview/status",
    response_class=JSONResponse,
)
def api_preview_status() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "process": preview_status(),
            "terrain_editor":
                terrain_editor_status(),
            "bridge": preview_bridge.status(),
            "social_dispatcher":
                preview_social_dispatcher_status(),
        }
    )


@router.post(
    "/api/preview/open",
    response_class=JSONResponse,
)
def api_preview_open() -> JSONResponse:
    try:
        state = start_preview()
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "error":
                    f"{type(exc).__name__}: {exc}",
            },
            status_code=500,
        )

    return JSONResponse(
        {
            **state,
            "bridge":
                preview_bridge.status(),
        }
    )


@router.post(
    "/api/terrain-editor/open",
    response_class=JSONResponse,
)
def api_terrain_editor_open() -> JSONResponse:
    try:
        state = start_terrain_editor()
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "error":
                    f"{type(exc).__name__}: {exc}",
            },
            status_code=500,
        )

    return JSONResponse(state)


@router.get(
    "/api/terrain-editor/status",
    response_class=JSONResponse,
)
def api_terrain_editor_status() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "process":
                terrain_editor_status(),
        }
    )



@router.post(
    "/api/preview/social-user",
    response_class=JSONResponse,
)
async def api_preview_social_user(
    request: Request,
) -> JSONResponse:
    try:
        payload: Any = (
            await request.json()
        )
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    bridge_state = (
        preview_bridge.status()
    )

    if not bridge_state.get("connected"):
        return JSONResponse(
            {
                "ok": False,
                "error":
                    "Preview ainda nao esta conectado.",
            },
            status_code=409,
        )

    user = normalize_social_user(
        payload
    )

    avatar_path = ""
    avatar_cache: dict[str, Any] = {
        "ok": False,
        "cached": False,
        "path": "",
    }

    if user.get("avatar_url"):
        avatar_cache = (
            await asyncio.to_thread(
                cache_profile_avatar,
                user["avatar_url"],
                user_key=(
                    user.get("user_id")
                    or user.get("username")
                    or "preview"
                ),
            )
        )

        if avatar_cache.get("ok"):
            avatar_path = str(
                avatar_cache.get("path")
                or ""
            )

    message = spectator_user_message(
        user,
        avatar_path=avatar_path,
        source="preview_social_test",
        preview=True,
    )

    message["time"] = time.time()

    try:
        sent = await preview_bridge.send(
            message
        )
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "sent": False,
                "error":
                    f"{type(exc).__name__}: {exc}",
            },
            status_code=500,
        )

    return JSONResponse(
        {
            "ok": bool(sent),
            "sent": bool(sent),
            "user": user,
            "avatar_cache": avatar_cache,
            "preview": True,
        }
    )



@router.post(
    "/api/preview/speech",
    response_class=JSONResponse,
)
async def api_preview_speech(
    request: Request,
) -> JSONResponse:
    try:
        payload: Any = (
            await request.json()
        )
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    text = str(
        payload.get("text")
        or ""
    ).strip()

    if not text:
        return JSONResponse(
            {
                "ok": False,
                "error": "Texto vazio.",
            },
            status_code=400,
        )

    if len(text) > 3000:
        return JSONResponse(
            {
                "ok": False,
                "error":
                    "Texto excede 3000 caracteres.",
            },
            status_code=400,
        )

    bridge_state = preview_bridge.status()

    if not bridge_state.get("connected"):
        return JSONResponse(
            {
                "ok": False,
                "error":
                    "Preview ainda nao esta conectado.",
            },
            status_code=409,
        )

    prepared = prepare_tts_input(
        text
    )

    try:
        speech = await asyncio.to_thread(
            synthesize_for_job,
            text,
        )
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "error":
                    f"{type(exc).__name__}: {exc}",
            },
            status_code=500,
        )

    timeline = (
        speech.get("timeline")
        if isinstance(
            speech.get("timeline"),
            dict,
        )
        else {}
    )

    job_id = (
        "preview-"
        + uuid.uuid4().hex
    )

    message = {
        "type": "speech_ready",
        "source": "preview_test",
        "time": time.time(),
        "payload": {
            "job_id": job_id,
            "text": prepared,
            "audio_path": str(
                speech.get("audio_path")
                or ""
            ),
            "segments": timeline.get(
                "segments",
                [],
            ),
            "timeline_end": float(
                timeline.get(
                    "timeline_end",
                    0.0,
                )
                or 0.0
            ),
            "speech_end": float(
                timeline.get(
                    "speech_end",
                    0.0,
                )
                or 0.0
            ),
            "trailing_mute_at": float(
                timeline.get(
                    "trailing_mute_at",
                    0.0,
                )
                or 0.0
            ),
            "metadata": {
                "source": "preview_test",
                "preview": True,
            },
        },
    }

    try:
        sent = await preview_bridge.send(
            message
        )
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "sent": False,
                "error":
                    f"{type(exc).__name__}: {exc}",
            },
            status_code=500,
        )

    return JSONResponse(
        {
            "ok": bool(sent),
            "sent": bool(sent),
            "job_id": job_id,
            "prepared": prepared,
            "chunks":
                speech.get("chunks", []),
        }
    )
