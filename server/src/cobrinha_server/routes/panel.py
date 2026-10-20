from __future__ import annotations

from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
)
from fastapi.templating import (
    Jinja2Templates,
)
from starlette.concurrency import (
    run_in_threadpool,
)

from cobrinha_server.bridge.godot_bridge import (
    godot_bridge,
)
from cobrinha_server.core.settings import (
    PROJECT_DIR,
)
from cobrinha_server.services import (
    content_updates,
    game_launcher,
    music_runtime,
    runtime_cleanup,
    system_updates,
    user_ai_settings,
)


router = APIRouter()

templates = Jinja2Templates(
    directory=str(
        PROJECT_DIR
        / "src"
        / "cobrinha_server"
        / "templates"
    )
)


def _live_runtime_active() -> bool:
    session = game_launcher.status()
    active_states = {"starting", "running", "stopping"}
    return (
        bool(session.get("running"))
        or str(session.get("state") or "").lower()
        in active_states
    )


def _cleanup_block_reason() -> str:
    if _live_runtime_active():
        return "A limpeza só pode ser executada com o jogo fechado."

    return ""


def _system_update_status() -> dict[str, object]:
    status = system_updates.public_status()
    live_active = _live_runtime_active()
    return {
        **status,
        "live_active": live_active,
        "can_install": (
            bool(status.get("update_available"))
            and not bool(status.get("busy"))
            and not live_active
        ),
    }


@router.get(
    "/api/system-updates",
    response_class=JSONResponse,
)
def api_system_updates_status() -> JSONResponse:
    return JSONResponse(_system_update_status())


@router.post(
    "/api/system-updates/check",
    response_class=JSONResponse,
)
async def api_system_updates_check() -> JSONResponse:
    try:
        await run_in_threadpool(
            system_updates.synchronize,
            install=False,
        )
    except system_updates.SystemUpdateBusy as exc:
        return JSONResponse(
            {**_system_update_status(), "ok": False, "error": str(exc)},
            status_code=409,
        )
    except Exception as exc:
        return JSONResponse(
            {**_system_update_status(), "ok": False, "error": str(exc)},
            status_code=502,
        )
    return JSONResponse(_system_update_status())


@router.post(
    "/api/system-updates/install",
    response_class=JSONResponse,
)
async def api_system_updates_install() -> JSONResponse:
    if _live_runtime_active():
        return JSONResponse(
            {
                **_system_update_status(),
                "ok": False,
                "error": "Feche o jogo antes de atualizar o sistema.",
            },
            status_code=409,
        )

    try:
        result = await run_in_threadpool(
            system_updates.synchronize,
            install=True,
        )
        if result.get("installed"):
            system_updates.schedule_restart()
            result = _system_update_status()
    except system_updates.SystemUpdateBusy as exc:
        return JSONResponse(
            {**_system_update_status(), "ok": False, "error": str(exc)},
            status_code=409,
        )
    except Exception as exc:
        return JSONResponse(
            {**_system_update_status(), "ok": False, "error": str(exc)},
            status_code=502,
        )
    return JSONResponse(result)


@router.get(
    "/api/content-updates",
    response_class=JSONResponse,
)
def api_content_updates_status() -> JSONResponse:
    return JSONResponse(content_updates.public_status())


@router.post(
    "/api/content-updates/check",
    response_class=JSONResponse,
)
async def api_content_updates_check() -> JSONResponse:
    try:
        result = await run_in_threadpool(
            content_updates.synchronize,
            install=False,
        )
    except content_updates.ContentUpdateBusy as exc:
        return JSONResponse(
            {**content_updates.public_status(), "ok": False, "error": str(exc)},
            status_code=409,
        )
    except Exception as exc:
        return JSONResponse(
            {**content_updates.public_status(), "ok": False, "error": str(exc)},
            status_code=502,
        )
    return JSONResponse(result)


@router.post(
    "/api/content-updates/install",
    response_class=JSONResponse,
)
async def api_content_updates_install() -> JSONResponse:
    try:
        result = await run_in_threadpool(
            content_updates.synchronize,
            install=True,
        )
    except (
        content_updates.ContentUpdateBusy,
        content_updates.ContentUpdateBlocked,
    ) as exc:
        return JSONResponse(
            {**content_updates.public_status(), "ok": False, "error": str(exc)},
            status_code=409,
        )
    except Exception as exc:
        return JSONResponse(
            {**content_updates.public_status(), "ok": False, "error": str(exc)},
            status_code=502,
        )
    return JSONResponse(result)


@router.post(
    "/api/content-updates/settings",
    response_class=JSONResponse,
)
async def api_content_updates_settings(
    request: Request,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    configuration = content_updates.update_configuration(
        auto_install=payload.get("auto_install", True),
    )
    return JSONResponse(
        {
            **content_updates.public_status(),
            "ok": True,
            "configuration": configuration,
        }
    )


@router.get(
    "/",
    response_class=HTMLResponse,
)
def panel(
    request: Request,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="panel.html",
        context={},
    )


@router.get(
    "/api/settings/openai",
    response_class=JSONResponse,
)
def api_openai_settings() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "settings": user_ai_settings.public_status(),
        }
    )


@router.post(
    "/api/settings/openai",
    response_class=JSONResponse,
)
async def api_openai_settings_update(
    request: Request,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        settings = user_ai_settings.update(payload)
    except ValueError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc)},
            status_code=400,
        )
    return JSONResponse(
        {"ok": True, "settings": settings}
    )


@router.get(
    "/api/maintenance/cleanup",
    response_class=JSONResponse,
)
async def api_cleanup_analysis() -> JSONResponse:
    analysis = await run_in_threadpool(runtime_cleanup.analyze)
    blocked_reason = _cleanup_block_reason()
    return JSONResponse(
        {
            **analysis,
            "live_active": _live_runtime_active(),
            "blocked": bool(blocked_reason),
            "blocked_reason": blocked_reason,
        }
    )


@router.post(
    "/api/maintenance/cleanup",
    response_class=JSONResponse,
)
async def api_cleanup_execute() -> JSONResponse:
    blocked_reason = _cleanup_block_reason()
    if blocked_reason:
        return JSONResponse(
            {
                "ok": False,
                "error": blocked_reason,
                "live_active": _live_runtime_active(),
            },
            status_code=409,
        )

    result = await run_in_threadpool(runtime_cleanup.cleanup)
    return JSONResponse(
        {
            **result,
            "live_active": False,
        },
        status_code=200 if result.get("ok") else 500,
    )


@router.get(
    "/api/music/runtime",
    response_class=JSONResponse,
)
def api_music_runtime_status() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "music":
                music_runtime.status(),
        }
    )


@router.post(
    "/api/music/runtime",
    response_class=JSONResponse,
)
async def api_music_runtime_update(
    request: Request,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    state = music_runtime.update(
        volume=(
            payload.get("volume")
            if "volume" in payload
            else None
        ),
        enabled=(
            payload.get("enabled")
            if "enabled" in payload
            else None
        ),
        current_track=(
            payload.get("current_track")
            if "current_track" in payload
            else None
        ),
    )

    message = (
        music_runtime.websocket_message()
    )

    official_sent = False

    try:
        official_sent = bool(
            await godot_bridge.send(
                message
            )
        )
    except Exception:
        official_sent = False

    return JSONResponse(
        {
            "ok": True,
            "music": state,
            "official_sent":
                official_sent,
        }
    )
