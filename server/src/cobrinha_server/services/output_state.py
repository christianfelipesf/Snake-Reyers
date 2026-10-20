from __future__ import annotations

from copy import deepcopy
from typing import Any

from cobrinha_server.services.output_plan import (
    build_plan,
)


_STATE: dict[str, Any] = {
    "running": False,
    "pid": 0,
    "started_at": 0.0,
    "stopped_at": 0.0,
    "last_error": "",
    "last_plan": {},
    "last_metrics": {},
}


def status() -> dict[str, Any]:
    state = deepcopy(_STATE)

    state["auto_start"] = False
    state["execution_enabled"] = False

    if not state["last_plan"]:
        state["last_plan"] = build_plan()

    return state


def remember_plan(
    plan: dict[str, Any],
) -> dict[str, Any]:
    _STATE["last_plan"] = deepcopy(
        plan or {}
    )

    return status()


def remember_metrics(
    metrics: dict[str, Any],
) -> dict[str, Any]:
    _STATE["last_metrics"] = deepcopy(
        metrics or {}
    )

    return status()


def reset_inert_state() -> dict[str, Any]:
    _STATE.update(
        {
            "running": False,
            "pid": 0,
            "started_at": 0.0,
            "stopped_at": 0.0,
            "last_error": "",
            "last_plan": {},
            "last_metrics": {},
        }
    )

    return status()
