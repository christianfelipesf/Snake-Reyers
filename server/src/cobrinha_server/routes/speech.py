from __future__ import annotations

import math
import struct
import time
import uuid
import wave
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from cobrinha_server.bridge.godot_bridge import (
    godot_bridge,
)
from cobrinha_server.core.settings import RUNS_DIR
from cobrinha_server.services.audio_timeline import (
    analyze_audio_timeline,
    build_audio_timeline_payload,
)


router = APIRouter()


def _write_synthetic_voice_test(
    output_path: Path,
) -> None:
    rate = 22050
    duration = 1.60
    total = int(rate * duration)
    frames = bytearray()

    for index in range(total):
        second = index / rate

        if 0.18 <= second < 0.48:
            amplitude = 6000
            frequency = 205.0
        elif 0.48 <= second < 0.62:
            amplitude = 0
            frequency = 205.0
        elif 0.62 <= second < 1.02:
            amplitude = 12500
            frequency = 235.0
        elif 1.02 <= second < 1.16:
            amplitude = 0
            frequency = 235.0
        elif 1.16 <= second < 1.43:
            amplitude = 8500
            frequency = 190.0
        else:
            amplitude = 0
            frequency = 190.0

        value = int(
            amplitude
            * math.sin(
                2.0
                * math.pi
                * frequency
                * second
            )
        )

        frames.extend(
            struct.pack(
                "<h",
                value,
            )
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with wave.open(
        str(output_path),
        "wb",
    ) as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)


@router.post(
    "/api/godot/speech-audio-test",
    response_class=JSONResponse,
)
async def speech_audio_test() -> JSONResponse:
    job_id = (
        "test-"
        + uuid.uuid4().hex[:12]
    )

    audio_dir = (
        RUNS_DIR
        / "speech_test"
    )

    audio_path = (
        audio_dir
        / f"{job_id}.wav"
    )

    _write_synthetic_voice_test(
        audio_path
    )

    timeline = analyze_audio_timeline(
        audio_path
    )

    timeline_payload = (
        build_audio_timeline_payload(
            audio_path,
            timeline,
        )
    )

    message = {
        "type": "speech_ready",
        "source": "synthetic_audio_test",
        "time": time.time(),
        "payload": {
            "job_id": job_id,
            "audio_path": str(
                audio_path.resolve()
            ),
            "segments": timeline_payload.get(
                "segments",
                [],
            ),
            "timeline_end": float(
                timeline_payload.get(
                    "timeline_end",
                    0.0,
                )
                or 0.0
            ),
            "speech_end": float(
                timeline_payload.get(
                    "speech_end",
                    0.0,
                )
                or 0.0
            ),
            "trailing_mute_at": float(
                timeline_payload.get(
                    "trailing_mute_at",
                    0.0,
                )
                or 0.0
            ),
        },
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
            "job_id": job_id,
            "audio_path": str(
                audio_path.resolve()
            ),
            "timeline": timeline_payload,
        }
    )
