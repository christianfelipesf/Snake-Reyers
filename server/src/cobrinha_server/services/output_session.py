from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_SAFE = re.compile(
    r"[^0-9A-Za-z_-]+"
)


def normalize_session_id(
    value: object,
) -> str:
    clean = _SAFE.sub(
        "_",
        str(value or "").strip(),
    ).strip("_")

    return (
        clean[:64]
        if clean
        else "session"
    )


@dataclass(frozen=True)
class OutputSession:
    session_id: str
    audio_sink: str
    audio_monitor: str
    display_name: str
    component_namespace: str


def build_session(
    session_id: object,
) -> OutputSession:
    clean = normalize_session_id(
        session_id
    )

    sink = (
        "cobrinha_live_"
        + clean
    )

    return OutputSession(
        session_id=clean,
        audio_sink=sink,
        audio_monitor=(
            sink + ".monitor"
        ),
        display_name=(
            "cobrinha_"
            + clean
        ),
        component_namespace=(
            "cobrinha_output_"
            + clean
        ),
    )


def validate_counts(
    observed: object,
) -> dict[str, Any]:
    data = (
        observed
        if isinstance(
            observed,
            dict,
        )
        else {}
    )

    keys = (
        "server_instances",
        "capture_workers",
        "game_instances",
        "display_instances",
        "audio_sinks",
        "audio_monitors",
    )

    mismatches = []

    for key in keys:
        actual = int(
            data.get(key)
            or 0
        )

        if actual != 1:
            mismatches.append(
                f"{key}:{actual}!=1"
            )

    return {
        "healthy":
            not mismatches,
        "mismatches":
            mismatches,
    }
