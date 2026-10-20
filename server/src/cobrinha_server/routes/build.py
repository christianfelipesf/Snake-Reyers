from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import (
    JSONResponse,
)

from cobrinha_server.services.godot_export import (
    build_status,
    start_export_build,
)


router = APIRouter()


@router.get(
    "/api/build/status",
    response_class=JSONResponse,
)
def api_build_status() -> JSONResponse:
    return JSONResponse(
        build_status()
    )


@router.post(
    "/api/build/godot",
    response_class=JSONResponse,
)
async def api_build_godot(
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

    status = start_export_build(
        use_for_live=bool(
            payload.get(
                "use_for_live",
                True,
            )
        ),
        force=bool(
            payload.get(
                "force",
                False,
            )
        ),
    )

    return JSONResponse(
        status,
        status_code=(
            200
            if status.get("ok", True)
            else 409
        ),
    )
