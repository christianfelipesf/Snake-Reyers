from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import (
    JSONResponse,
)

from cobrinha_server.services.output_metrics import (
    evaluate,
)
from cobrinha_server.services.output_plan import (
    build_plan,
)
from cobrinha_server.services.output_state import (
    remember_metrics,
    remember_plan,
    status,
)


router = APIRouter()


@router.get(
    "/api/output/status",
    response_class=JSONResponse,
)
def api_output_status() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "output": status(),
        }
    )


@router.post(
    "/api/output/plan",
    response_class=JSONResponse,
)
async def api_output_plan(
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
        payload.get("config")
        if isinstance(
            payload.get("config"),
            dict,
        )
        else {}
    )

    destination_url = str(
        payload.get(
            "destination_url"
        )
        or ""
    ).strip()

    plan = build_plan(
        config,
        destination_url=
            destination_url,
    )

    remember_plan(
        plan
    )

    return JSONResponse(
        {
            "ok": True,
            "plan": plan,
        }
    )


@router.post(
    "/api/output/metrics/evaluate",
    response_class=JSONResponse,
)
async def api_output_metrics(
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

    metrics = evaluate(
        payload
    )

    remember_metrics(
        metrics
    )

    return JSONResponse(
        {
            "ok": True,
            "metrics": metrics,
        }
    )
