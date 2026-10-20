from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cobrinha_server.services.speech_dispatcher import (
    dispatch_once,
    dispatcher_running,
)
from cobrinha_server.services.speech_queue import (
    enqueue_manual_sequence,
    status as queue_status,
)
from cobrinha_server.services.tts_service import (
    prepare_tts_input,
    safe_tts_chunks,
    tts_model_loaded,
    voice_ready,
)
from cobrinha_server.services.tts_worker import (
    worker_status,
)


router = APIRouter()


@router.get(
    "/api/speech/status",
    response_class=JSONResponse,
)
def api_speech_status() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "queue": queue_status(),
            "dispatcher_running":
                dispatcher_running(),
            "worker": worker_status(),
            "voice_ready": voice_ready(),
            "tts_model_loaded":
                tts_model_loaded(),
        }
    )


@router.post(
    "/api/speech/prepare-text",
    response_class=JSONResponse,
)
async def api_speech_prepare_text(
    request: Request,
) -> JSONResponse:
    try:
        payload: Any = (
            await request.json()
        )
    except Exception:
        payload = {}

    if not isinstance(
        payload,
        dict,
    ):
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

    prepared = prepare_tts_input(
        text
    )

    chunks = safe_tts_chunks(
        text,
        max_chars=150,
    )

    return JSONResponse(
        {
            "ok": True,
            "original": text,
            "prepared": prepared,
            "chunks": chunks,
            "parts_total": len(chunks),
        }
    )


@router.post(
    "/api/speech/manual",
    response_class=JSONResponse,
)
async def api_speech_manual(
    request: Request,
) -> JSONResponse:
    try:
        payload: Any = (
            await request.json()
        )
    except Exception:
        payload = {}

    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    text = str(
        payload.get("text")
        or ""
    ).strip()

    if not text:
        return JSONResponse(
            {
                "ok": False,
                "error":
                    "Texto manual vazio.",
            },
            status_code=400,
        )

    if len(text) > 3000:
        return JSONResponse(
            {
                "ok": False,
                "error":
                    "Texto manual excede 3000 caracteres.",
            },
            status_code=400,
        )

    try:
        sequence = enqueue_manual_sequence(
            text,
            priority=90,
        )
    except RuntimeError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
                "queue": queue_status(),
            },
            status_code=409,
        )
    except ValueError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status_code=400,
        )

    return JSONResponse(
        {
            "ok": True,
            "manual_sequence": sequence,
            "parts": int(
                sequence.get("chunk_count")
                or sequence.get("parts_total")
                or 0
            ),
            "queue": queue_status(),
        }
    )


@router.post(
    "/api/speech/dispatch-next",
    response_class=JSONResponse,
)
async def api_dispatch_next() -> JSONResponse:
    result = await dispatch_once()

    return JSONResponse(
        {
            "ok": True,
            **result,
        }
    )
