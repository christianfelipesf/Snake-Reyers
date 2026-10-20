from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import (
    JSONResponse,
)
from starlette.concurrency import (
    run_in_threadpool,
)

from cobrinha_server.services import (
    game_launcher,
)
from cobrinha_server.services.session_control import (
    CONFIG_FIELDS,
    public_config,
    save_config,
)


router = APIRouter()


@router.get(
    "/api/session/status",
    response_class=JSONResponse,
)
def api_session_status() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "session": game_launcher.status(),
            "config": public_config(),
        }
    )


@router.get(
    "/api/session/config",
    response_class=JSONResponse,
)
def api_session_config() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "config": public_config(),
        }
    )


@router.post(
    "/api/session/config",
    response_class=JSONResponse,
)
async def api_session_config_save(
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

    config = save_config(
        payload
    )

    return JSONResponse(
        {
            "ok": True,
            "config": config,
        }
    )


@router.post(
    "/api/session/start",
    response_class=JSONResponse,
)
async def api_session_start(
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

    config = (
        save_config(payload)
        if any(
            key in payload
            for key in CONFIG_FIELDS
        )
        else public_config()
    )

    result = await run_in_threadpool(
        game_launcher.start,
        config,
    )

    return JSONResponse(
        result,
        status_code=(
            200 if result.get("ok") else 500
        ),
    )


@router.post(
    "/api/session/stop",
    response_class=JSONResponse,
)
async def api_session_stop() -> JSONResponse:
    result = await run_in_threadpool(
        game_launcher.stop
    )

    return JSONResponse(
        result,
        status_code=(
            200 if result.get("ok") else 500
        ),
    )
