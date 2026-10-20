from __future__ import annotations

import time
from typing import Any

from cobrinha_server.bridge.godot_bridge import (
    godot_bridge,
)


HEART_ME_BAND_SHOWCASE_DEFAULT_SECONDS = 10.0
HEART_ME_BAND_SHOWCASE_GRACE_SECONDS = 0.75
HEART_ME_BAND_SHOWCASE_MAX_SECONDS = 15.0


def _clean_float(
    value: object,
    fallback: float,
) -> float:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return fallback


def _last_event(
    bridge_state: dict[str, Any],
    event_type: str,
) -> dict[str, Any]:
    last_by_type = bridge_state.get(
        "last_by_type",
        {},
    )
    if not isinstance(
        last_by_type,
        dict,
    ):
        return {}

    event = last_by_type.get(
        event_type,
        {},
    )
    if not isinstance(
        event,
        dict,
    ):
        return {}

    return event


def _event_received_at(
    event: dict[str, Any],
) -> float:
    return _clean_float(
        event.get("_received_at"),
        0.0,
    )


def heart_me_band_music_showcase_active(
    bridge_state: dict[str, Any] | None = None,
    *,
    now: float | None = None,
) -> bool:
    state = (
        bridge_state
        if bridge_state is not None
        else godot_bridge.status()
    )
    if not bool(
        state.get("connected")
    ):
        return False

    started = _last_event(
        state,
        "heart_me_band_music_showcase_started",
    )
    if not started:
        return False

    started_at = _event_received_at(
        started
    )
    if started_at <= 0.0:
        return False

    finished = _last_event(
        state,
        "heart_me_band_music_showcase_finished",
    )
    if (
        finished
        and _event_received_at(finished) >= started_at
    ):
        return False

    duration = _clean_float(
        started.get("duration_seconds"),
        HEART_ME_BAND_SHOWCASE_DEFAULT_SECONDS,
    )
    duration = max(
        0.0,
        min(
            HEART_ME_BAND_SHOWCASE_MAX_SECONDS,
            duration,
        ),
    )
    current_time = (
        time.time()
        if now is None
        else now
    )

    return (
        current_time - started_at
        <= duration + HEART_ME_BAND_SHOWCASE_GRACE_SECONDS
    )
