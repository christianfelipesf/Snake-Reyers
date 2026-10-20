from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import (
    JSONResponse,
)

from cobrinha_server.core.settings import (
    TIKTOK_MONITOR_HOST,
    TIKTOK_MONITOR_PORT,
)
from cobrinha_server.services import (
    live_events,
    song_runtime,
    tiktok_monitor,
    top_supporters,
)
from cobrinha_server.services.event_decision_worker import (
    start_event_decision_worker,
    status as event_decision_worker_status,
)
from cobrinha_server.services.live_session_state import (
    reset_live_transient_state,
)
from cobrinha_server.services.session_control import (
    save_config,
)


router = APIRouter()


@router.get(
    "/api/monitor/status",
    response_class=JSONResponse,
)
def api_monitor_status() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "monitor":
                tiktok_monitor.status(),
            "events":
                live_events.status(),
            "top_supporters":
                top_supporters.status(),
            "gift_audio":
                song_runtime.gift_audio_diagnostics(),
            "event_decision_worker":
                event_decision_worker_status(),
            "social_dispatcher":
                event_decision_worker_status(),
        }
    )


@router.post(
    "/api/monitor/start",
    response_class=JSONResponse,
)
async def api_monitor_start(
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

    username = str(
        payload.get("username")
        or ""
    ).strip()

    server_url = str(
        payload.get("server_url")
        or (
            "http://"
            f"{TIKTOK_MONITOR_HOST}:"
            f"{TIKTOK_MONITOR_PORT}"
        )
    ).strip()

    prepare_local_node = bool(
        payload.get(
            "prepare_local_node",
            False,
        )
    )

    if username:
        save_config(
            {
                "username": username,
                "monitor_server": server_url,
            }
        )

    runtime_reset = reset_live_transient_state(
        reason="monitor_start",
    )

    state = (
        tiktok_monitor.start_monitor(
            username,
            server_url=server_url,
            prepare_local_node=
                prepare_local_node,
        )
    )

    worker_state = (
        start_event_decision_worker()
        if state.get("running")
        else event_decision_worker_status()
    )

    return JSONResponse(
        {
            "ok": bool(
                state.get("running")
            ),
            "monitor": state,
            "runtime_reset": runtime_reset,
            "event_decision_worker":
                worker_state,
            "social_dispatcher":
                worker_state,
        }
    )


@router.post(
    "/api/monitor/stop",
    response_class=JSONResponse,
)
async def api_monitor_stop(
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

    stop_local_node_runtime = bool(
        payload.get(
            "stop_local_node_runtime",
            False,
        )
    )

    state = (
        tiktok_monitor.stop_monitor(
            stop_local_node_runtime=
                stop_local_node_runtime,
        )
    )
    runtime_reset = reset_live_transient_state(
        reason="monitor_stop",
    )

    return JSONResponse(
        {
            "ok": True,
            "monitor": state,
            "runtime_reset": runtime_reset,
            "event_decision_worker":
                event_decision_worker_status(),
            "social_dispatcher":
                event_decision_worker_status(),
        }
    )


@router.post(
    "/api/monitor/synthetic/comment",
    response_class=JSONResponse,
)
async def api_synthetic_comment(
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

    result = (
        tiktok_monitor
        .ingest_comment(
            payload
        )
    )

    return JSONResponse(
        result,
        status_code=(
            200
            if result.get("ok")
            else 400
        ),
    )


@router.post(
    "/api/monitor/synthetic/like",
    response_class=JSONResponse,
)
async def api_synthetic_like(
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

    result = (
        tiktok_monitor.ingest_like(
            payload
        )
    )

    return JSONResponse(
        result,
        status_code=(
            200
            if result.get("ok")
            else 400
        ),
    )


@router.post(
    "/api/monitor/synthetic/share",
    response_class=JSONResponse,
)
async def api_synthetic_share(
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

    result = (
        tiktok_monitor.ingest_share(
            payload
        )
    )

    return JSONResponse(
        result,
        status_code=(
            200
            if result.get("ok")
            else 400
        ),
    )


@router.post(
    "/api/monitor/synthetic/gift",
    response_class=JSONResponse,
)
async def api_synthetic_gift(
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

    result = (
        tiktok_monitor.ingest_gift(
            payload
        )
    )

    return JSONResponse(
        result,
        status_code=(
            200
            if result.get("ok")
            else 400
        ),
    )
