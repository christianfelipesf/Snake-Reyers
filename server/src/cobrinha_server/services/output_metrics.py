from __future__ import annotations

from typing import Any


def _number(
    value: object,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _integer(
    value: object,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def evaluate(
    raw: object,
) -> dict[str, Any]:
    data = (
        raw
        if isinstance(raw, dict)
        else {}
    )

    now = _number(
        data.get("now"),
        0.0,
    )

    started_at = _number(
        data.get("started_at"),
        0.0,
    )

    first_stat_at = _number(
        data.get("first_stat_at"),
        0.0,
    )

    last_ack_at = _number(
        data.get("last_ack_at"),
        0.0,
    )

    out_total = max(
        0,
        _integer(
            data.get("out_total"),
            0,
        ),
    )

    out_acked = max(
        0,
        _integer(
            data.get("out_acked"),
            0,
        ),
    )

    queue_audio_current = max(
        0,
        _integer(
            data.get(
                "queue_audio_current"
            ),
            0,
        ),
    )

    queue_audio_max = max(
        0,
        _integer(
            data.get(
                "queue_audio_max"
            ),
            0,
        ),
    )

    queue_video_current = max(
        0,
        _integer(
            data.get(
                "queue_video_current"
            ),
            0,
        ),
    )

    queue_video_max = max(
        0,
        _integer(
            data.get(
                "queue_video_max"
            ),
            0,
        ),
    )

    clock_name = str(
        data.get("clock_name")
        or ""
    ).strip()

    no_ack_timeout = max(
        5.0,
        _number(
            data.get(
                "no_ack_timeout"
            ),
            35.0,
        ),
    )

    stale_ack_timeout = max(
        5.0,
        _number(
            data.get(
                "stale_ack_timeout"
            ),
            45.0,
        ),
    )

    no_ack_min_bytes = max(
        0,
        _integer(
            data.get(
                "no_ack_min_bytes"
            ),
            5_000_000,
        ),
    )

    stale_ack_min_bytes = max(
        no_ack_min_bytes,
        _integer(
            data.get(
                "stale_ack_min_bytes"
            ),
            30_000_000,
        ),
    )

    unacked = max(
        0,
        out_total - out_acked,
    )

    runtime_age = (
        max(
            0.0,
            now - started_at,
        )
        if (
            now > 0.0
            and started_at > 0.0
        )
        else 0.0
    )

    stat_age = (
        max(
            0.0,
            now - first_stat_at,
        )
        if (
            now > 0.0
            and first_stat_at > 0.0
        )
        else 0.0
    )

    ack_age = (
        max(
            0.0,
            now - last_ack_at,
        )
        if (
            now > 0.0
            and last_ack_at > 0.0
        )
        else 0.0
    )

    no_ack = bool(
        out_total
        >= no_ack_min_bytes
        and out_acked <= 0
        and first_stat_at > 0.0
        and stat_age >= no_ack_timeout
    )

    stale_ack = bool(
        out_total
        >= stale_ack_min_bytes
        and out_acked > 0
        and last_ack_at > 0.0
        and ack_age >= stale_ack_timeout
        and unacked > 0
    )

    audio_queue_ratio = (
        float(queue_audio_current)
        / float(queue_audio_max)
        if queue_audio_max > 0
        else 0.0
    )

    video_queue_ratio = (
        float(queue_video_current)
        / float(queue_video_max)
        if queue_video_max > 0
        else 0.0
    )

    audio_queue_pressure = (
        audio_queue_ratio >= 0.85
    )

    video_queue_pressure = (
        video_queue_ratio >= 0.85
    )

    clock_present = bool(
        clock_name
    )

    healthy = not any(
        (
            stale_ack,
            audio_queue_pressure,
            video_queue_pressure,
            not clock_present,
        )
    )

    reason = ""

    if no_ack:
        reason = "remote_ack_pending"
    elif stale_ack:
        reason = "remote_ack_stale"
    elif audio_queue_pressure:
        reason = "audio_queue_pressure"
    elif video_queue_pressure:
        reason = "video_queue_pressure"
    elif not clock_present:
        reason = "clock_missing"

    return {
        "healthy": healthy,
        "reason": reason,
        "runtime_age": round(
            runtime_age,
            3,
        ),
        "clock": {
            "name": clock_name,
            "present": clock_present,
        },
        "remote_ack": {
            "out_total": out_total,
            "out_acked": out_acked,
            "unacked": unacked,
            "first_stat_at":
                first_stat_at,
            "last_ack_at":
                last_ack_at,
            "stat_age": round(
                stat_age,
                3,
            ),
            "ack_age": round(
                ack_age,
                3,
            ),
            "no_initial_ack":
                no_ack,
            "stale_ack":
                stale_ack,
        },
        "queues": {
            "audio": {
                "current":
                    queue_audio_current,
                "max":
                    queue_audio_max,
                "ratio": round(
                    audio_queue_ratio,
                    4,
                ),
                "pressure":
                    audio_queue_pressure,
                "leaky": False,
            },
            "video": {
                "current":
                    queue_video_current,
                "max":
                    queue_video_max,
                "ratio": round(
                    video_queue_ratio,
                    4,
                ),
                "pressure":
                    video_queue_pressure,
                "leaky": False,
            },
            "post_container": {
                "leaky": False,
            },
        },
        "invariants": {
            "audiorate": True,
            "sink_sync": True,
            "audio_queue_leaky":
                False,
            "post_container_queue_leaky":
                False,
        },
    }
