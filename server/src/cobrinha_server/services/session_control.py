from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cobrinha_server.core.json_store import (
    read_json,
    write_json_atomic,
)
from cobrinha_server.core.settings import (
    SESSION_CONTROL_CONFIG_FILE,
    TIKTOK_MONITOR_HOST,
    TIKTOK_MONITOR_PORT,
)
from cobrinha_server.services.session_executor_plan import (
    preferred_live_executable,
)


CONFIG_FIELDS = {
    "username",
    "monitor_server",
    "game_runtime",
    "godot_executable",
    "display",
}


def _default_config() -> dict[str, Any]:
    return {
        "username": "",
        "monitor_server": (
            "http://"
            f"{TIKTOK_MONITOR_HOST}:"
            f"{TIKTOK_MONITOR_PORT}"
        ),
        "game_runtime": "build",
        "godot_executable":
            preferred_live_executable(),
        "display": "",
    }


def _normalize_game_runtime(
    value: object,
) -> str:
    if os.name == "nt":
        return "build"

    clean = str(
        value
        or ""
    ).strip().casefold()

    if clean in {
        "editor",
        "godot",
        "project",
        "projeto",
    }:
        return "editor"

    return "build"


def _raw_config() -> dict[str, Any]:
    raw = read_json(
        Path(
            SESSION_CONTROL_CONFIG_FILE
        ),
        {},
    )

    if not isinstance(raw, dict):
        return {}

    return dict(raw)


def sanitize_config(
    raw: dict[str, Any] | None,
) -> dict[str, Any]:
    source = {
        **_default_config(),
        **(
            dict(raw)
            if isinstance(raw, dict)
            else {}
        ),
    }

    game_runtime = _normalize_game_runtime(
        source.get("game_runtime")
    )

    return {
        "username": str(
            source.get("username")
            or ""
        ).strip().lstrip("@"),
        "monitor_server": str(
            source.get("monitor_server")
            or _default_config()["monitor_server"]
        ).strip(),
        "game_runtime": game_runtime,
        "godot_executable":
            preferred_live_executable(
                source.get("godot_executable"),
                game_runtime,
            ),
        "display": str(
            source.get("display")
            or ""
        ).strip(),
    }


def save_config(
    updates: dict[str, Any],
) -> dict[str, Any]:
    raw = _raw_config()
    clean_updates = {
        key: value
        for key, value in dict(
            updates
            or {}
        ).items()
        if key in CONFIG_FIELDS
    }

    merged = {
        **raw,
        **clean_updates,
    }
    sanitized = sanitize_config(
        merged
    )
    output = {
        **raw,
        **sanitized,
    }

    write_json_atomic(
        Path(
            SESSION_CONTROL_CONFIG_FILE
        ),
        output,
    )

    return dict(sanitized)


def config_from_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}

    config = public_config()
    overrides = {
        key: payload.get(key)
        for key in CONFIG_FIELDS
        if key in payload
    }

    if overrides:
        config = sanitize_config(
            {
                **config,
                **overrides,
            }
        )

    return config


def load_config() -> dict[str, Any]:
    return sanitize_config(
        _raw_config()
    )


def public_config() -> dict[str, Any]:
    return dict(
        load_config()
    )
