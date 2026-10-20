from __future__ import annotations

import asyncio
from typing import Any

from cobrinha_server.bridge.godot_bridge import (
    godot_bridge,
)
from cobrinha_server.services import (
    godot_runtime_state,
    song_runtime,
)
from cobrinha_server.services.speech_queue import (
    acknowledge_speech_finished,
    active_job,
    pop_next,
    return_active_to_ready,
)


_TASK: asyncio.Task[None] | None = None


def start_speech_dispatcher() -> None:
    global _TASK

    if (
        _TASK is not None
        and not _TASK.done()
    ):
        return

    _TASK = asyncio.create_task(
        _dispatcher_loop(),
        name="cobrinha-speech-dispatcher",
    )


def dispatcher_running() -> bool:
    return (
        _TASK is not None
        and not _TASK.done()
    )


async def _dispatcher_loop() -> None:
    while True:
        await dispatch_once()
        await asyncio.sleep(0.10)


async def dispatch_once() -> dict[str, Any]:
    bridge_state = godot_bridge.status()

    if not bridge_state.get(
        "connected"
    ):
        return {
            "sent": False,
            "reason": "godot_disconnected",
        }

    if active_job() is not None:
        return {
            "sent": False,
            "reason": "speech_active",
        }

    if song_runtime.singing_active():
        return {
            "sent": False,
            "reason": "song_active",
        }

    if godot_runtime_state.heart_me_band_music_showcase_active(
        bridge_state
    ):
        return {
            "sent": False,
            "reason": "heart_me_band_music_showcase_active",
        }

    job = pop_next()

    if job is None:
        return {
            "sent": False,
            "reason": "ready_empty",
        }

    job_id = str(
        job.get("id")
        or ""
    )

    if job.get("prepare_error"):
        acknowledge_speech_finished(
            job_id
        )

        return {
            "sent": False,
            "reason": "prepare_error",
            "job_id": job_id,
        }

    timeline = (
        job.get("timeline")
        if isinstance(
            job.get("timeline"),
            dict,
        )
        else {}
    )

    message = {
        "type": "speech_ready",
        "source": "speech_queue",
        "payload": {
            "job_id": job_id,
            "text": str(
                job.get("text")
                or ""
            ),
            "audio_path": str(
                job.get("audio_path")
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
            "metadata": (
                job.get("metadata")
                if isinstance(
                    job.get("metadata"),
                    dict,
                )
                else {}
            ),
        },
    }

    try:
        sent = await godot_bridge.send(
            message
        )
    except Exception as exc:
        sent = False
        error = (
            f"{type(exc).__name__}: {exc}"
        )
    else:
        error = ""

    if not sent:
        return_active_to_ready(
            job_id
        )

    return {
        "sent": bool(sent),
        "job_id": job_id,
        "error": error,
        "message": message,
    }
