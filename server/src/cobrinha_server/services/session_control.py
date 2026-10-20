from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from cobrinha_server.core.settings import (
    SESSION_CONTROL_CONFIG_FILE,
    TIKTOK_MONITOR_HOST,
    TIKTOK_MONITOR_PORT,
)
from cobrinha_server.core.json_store import (
    read_json,
    write_json_atomic,
)
from cobrinha_server.services import (
    tiktok_monitor,
)
from cobrinha_server.services.output_state import (
    status as output_status,
)
from cobrinha_server.services.streamlabs_adapter import (
    public_status as streamlabs_status,
)
from cobrinha_server.services.session_executor import (
    build_execution_preview,
    status as executor_status,
)
from cobrinha_server.services.session_executor_plan import (
    preferred_live_executable,
)
from cobrinha_server.services.session_runtime_adapters import (
    build_all_specs_preview,
    public_runtime_capabilities,
)
from cobrinha_server.services.session_runtime_orchestrator import (
    status as runtime_orchestrator_status,
)
from cobrinha_server.services.session_real_bridge import (
    public_status as session_real_bridge_status,
)


_STATE: dict[str, Any] = {
    "state": "stopped",
    "message": "",
    "monitor_auto": True,
    "monitor_ready": False,
    "output_ready": False,
    "credential_ready": False,
    "last_error": "",
}

CONFIG_FIELDS = {
    "enabled",
    "username",
    "monitor_server",
    "auto_streamlabs",
    "auto_start_enabled",
    "mode",
    "title",
    "game",
    "audience_type",
    "video_encoder",
    "game_runtime",
    "godot_executable",
    "rtmp_sink",
    "video_bitrate",
    "display",
    "start_min_seconds",
    "start_max_seconds",
    "stop_min_seconds",
    "stop_max_seconds",
}


def _default_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "username": "",
        "monitor_server":
            (
                "http://"
                f"{TIKTOK_MONITOR_HOST}:"
                f"{TIKTOK_MONITOR_PORT}"
            ),
        "auto_streamlabs": True,
        "auto_start_enabled": False,
        "mode": "normal",
        "title": "",
        "game": "",
        "audience_type": "0",
        "video_encoder": "nvenc",
        "game_runtime": "build",
        "godot_executable":
            preferred_live_executable(),
        "rtmp_sink": "rtmp2sink",
        "video_bitrate": 2500,
        "display": ":0",
        "start_min_seconds": 900,
        "start_max_seconds": 1500,
        "stop_min_seconds": 1620,
        "stop_max_seconds": 2100,
    }


def _normalize_mode(value: object) -> str:
    clean = str(value or "").strip().casefold()
    if clean in {"battle", "batalha", "batalha_hdmi", "hdmi"}:
        return "battle"
    return "normal"


def _normalize_panel_encoder(value: object) -> str:
    clean = str(value or "").strip().casefold()
    if clean in {"auto", "nvenc", "x264"}:
        return clean
    if clean in {"nvidia", "nvh264", "nvh264enc"}:
        return "nvenc"
    if clean in {"x264enc", "cpu"}:
        return "x264"
    return "nvenc"


def _normalize_panel_sink(value: object) -> str:
    clean = str(value or "").strip().casefold()
    if clean in {"auto", "rtmp2sink", "rtmpsink"}:
        return clean
    return "rtmp2sink"


def _normalize_game_runtime(value: object) -> str:
    clean = str(value or "").strip().casefold()
    if clean in {
        "editor",
        "godot",
        "project",
        "projeto",
    }:
        return "editor"
    return "build"


def _safe_int(
    value: object,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        number = int(
            float(
                value
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        number = int(default)

    return max(
        int(minimum),
        min(
            int(maximum),
            number,
        ),
    )


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

    return {
        "enabled": bool(
            source.get("enabled", False)
        ),
        "username": str(
            source.get("username")
            or ""
        ).strip().lstrip("@"),
        "monitor_server": str(
            source.get("monitor_server")
            or (
                "http://"
                f"{TIKTOK_MONITOR_HOST}:"
                f"{TIKTOK_MONITOR_PORT}"
            )
        ).strip(),
        "auto_streamlabs": bool(
            source.get(
                "auto_streamlabs",
                True,
            )
        ),
        "auto_start_enabled": bool(
            source.get(
                "auto_start_enabled",
                False,
            )
        ),
        "mode":
            _normalize_mode(
                source.get("mode")
            ),
        "title": str(
            source.get("title")
            or ""
        ).strip(),
        "game": str(
            source.get("game")
            or ""
        ).strip(),
        "audience_type": str(
            source.get("audience_type")
            or "0"
        ).strip(),
        "video_encoder":
            _normalize_panel_encoder(
                source.get(
                    "video_encoder"
                )
            ),
        "game_runtime":
            _normalize_game_runtime(
                source.get(
                    "game_runtime"
                )
            ),
        "godot_executable":
            preferred_live_executable(
                source.get(
                    "godot_executable"
                ),
                source.get(
                    "game_runtime"
                ),
            ),
        "rtmp_sink":
            _normalize_panel_sink(
                source.get("rtmp_sink")
            ),
        "video_bitrate":
            _safe_int(
                source.get(
                    "video_bitrate"
                ),
                2500,
                minimum=500,
                maximum=12000,
            ),
        "display": str(
            source.get("display")
            or ":0"
        ).strip(),
        "start_min_seconds":
            _safe_int(
                source.get(
                    "start_min_seconds"
                ),
                900,
                minimum=60,
                maximum=86400,
            ),
        "start_max_seconds":
            _safe_int(
                source.get(
                    "start_max_seconds"
                ),
                1500,
                minimum=60,
                maximum=86400,
            ),
        "stop_min_seconds":
            _safe_int(
                source.get(
                    "stop_min_seconds"
                ),
                1620,
                minimum=60,
                maximum=86400,
            ),
        "stop_max_seconds":
            _safe_int(
                source.get(
                    "stop_max_seconds"
                ),
                2100,
                minimum=60,
                maximum=86400,
            ),
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

    if (
        "auto_start_enabled" in clean_updates
        and "enabled" not in clean_updates
    ):
        clean_updates["enabled"] = bool(
            clean_updates.get(
                "auto_start_enabled"
            )
        )

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


def status() -> dict[str, Any]:
    monitor = (
        tiktok_monitor.status()
    )

    output = output_status()

    streamlabs = (
        streamlabs_status()
    )

    runtime_orchestrator = (
        runtime_orchestrator_status()
    )

    real_bridge = (
        session_real_bridge_status()
    )

    runtime_state = str(
        runtime_orchestrator.get(
            "state"
        )
        or ""
    )

    runtime_active = (
        runtime_state
        in {
            "starting",
            "running",
            "rollback_partial",
        }
        or bool(
            runtime_orchestrator.get(
                "game"
            )
        )
        or bool(
            runtime_orchestrator.get(
                "capture"
            )
        )
        or bool(
            runtime_orchestrator.get(
                "monitor_started"
            )
        )
    )

    control_state = str(
        _STATE.get(
            "state",
            "stopped",
        )
        or "stopped"
    )

    effective_state = (
        runtime_state
        if runtime_active
        and runtime_state
        else control_state
    )

    return {
        **_STATE,
        "state":
            effective_state,
        "control_state":
            control_state,
        "config":
            public_config(),
        "monitor": {
            "running":
                bool(
                    monitor.get(
                        "running"
                    )
                ),
            "connected":
                bool(
                    monitor.get(
                        "connected"
                    )
                ),
            "listening":
                bool(
                    monitor.get(
                        "listening"
                    )
                ),
        },
        "output": {
            "running":
                bool(
                    output.get(
                        "running"
                    )
                ),
            "execution_enabled":
                bool(
                    output.get(
                        "execution_enabled"
                    )
                ),
        },
        "streamlabs":
            streamlabs,
        "executor":
            executor_status(),
        "runtime_orchestrator":
            runtime_orchestrator,
        "runtime_capabilities":
            public_runtime_capabilities(),
        "real_bridge":
            real_bridge,
    }


def executor_preview(
    *,
    session_id: str,
    executable: str,
    server_url: str,
    display_value: str,
) -> dict[str, Any]:
    return build_execution_preview(
        session_id=session_id,
        executable=executable,
        server_url=server_url,
        display_value=display_value,
    )


def normalize_runtime_encoder(
    value: str,
) -> str:
    normalized = str(
        value
        or ""
    ).strip().casefold()

    aliases = {
        "auto": "nvh264enc",
        "nvenc": "nvh264enc",
        "nvh264": "nvh264enc",
        "nvh264enc": "nvh264enc",
        "nvidia": "nvh264enc",
        "x264": "x264enc",
        "x264enc": "x264enc",
        "cpu": "x264enc",
    }

    return aliases.get(
        normalized,
        "x264enc",
    )


def normalize_runtime_sink(
    value: str,
) -> str:
    normalized = str(
        value
        or ""
    ).strip().casefold()

    aliases = {
        "auto": "rtmp2sink",
        "rtmp": "rtmp2sink",
        "rtmp2": "rtmp2sink",
        "rtmp2sink": "rtmp2sink",
        "rtmpsink": "rtmpsink",
    }

    return aliases.get(
        normalized,
        "rtmp2sink",
    )


def runtime_preview(
    *,
    session_id: str,
    executable: str,
    server_url: str,
    display_value: str,
    encoder: str,
    sink: str,
    bitrate_kbps: int,
) -> dict[str, Any]:
    return build_all_specs_preview(
        session_id=session_id,
        executable=executable,
        server_url=server_url,
        display_value=display_value,
        destination_url=(
            "rtmps://preview.invalid/live/"
            "PREVIEW_NOT_A_REAL_CREDENTIAL"
        ),
        encoder=normalize_runtime_encoder(
            encoder
        ),
        sink=normalize_runtime_sink(
            sink
        ),
        bitrate_kbps=bitrate_kbps,
    )


def build_sequence() -> list[str]:
    config = load_config()

    result = [
        "validate_config",
        "prepare_session",
        "prepare_game_audio",
        "open_game_window",
        "wait_game_bridge_ready",
        "wait_game_audio_ready",
        "prepare_monitor_runtime",
        "connect_monitor",
        "wait_monitor_ready",
    ]

    if config.get(
        "auto_streamlabs"
    ):
        result.append(
            "acquire_fresh_streamlabs_credential"
        )

    result.extend(
        [
            "prepare_output",
            "activate_game_bridge",
            "mark_session_running",
        ]
    )

    return result


def simulate_begin(
    *,
    monitor_probe: Callable[
        [dict[str, Any]],
        dict[str, Any],
    ],
    credential_probe: Callable[
        [dict[str, Any]],
        dict[str, Any],
    ]
    | None = None,
    output_probe: Callable[
        [dict[str, Any]],
        dict[str, Any],
    ],
) -> dict[str, Any]:
    config = load_config()

    username = str(
        config.get("username")
        or ""
    ).strip()

    if not username:
        return {
            "ok": False,
            "state": "blocked",
            "reason":
                "missing_username",
            "sequence":
                build_sequence(),
        }

    _STATE.update(
        {
            "state":
                "preparing_monitor",
            "message":
                "Preparando monitor.",
            "monitor_ready":
                False,
            "output_ready":
                False,
            "credential_ready":
                False,
            "last_error":
                "",
        }
    )

    monitor_result = (
        monitor_probe(
            {
                "username":
                    username,
                "server_url":
                    config.get(
                        "monitor_server"
                    ),
                "prepare_local_node":
                    True,
            }
        )
    )

    monitor_ready = bool(
        monitor_result.get("ready")
        or monitor_result.get(
            "listening"
        )
    )

    if not monitor_ready:
        _STATE.update(
            {
                "state":
                    "blocked_monitor",
                "last_error":
                    "monitor_not_ready",
            }
        )

        return {
            "ok": False,
            "state":
                "blocked_monitor",
            "monitor":
                monitor_result,
            "sequence":
                build_sequence(),
        }

    _STATE[
        "monitor_ready"
    ] = True

    credential_result: dict[
        str,
        Any,
    ] = {
        "required": False,
        "ready": True,
    }

    if config.get(
        "auto_streamlabs"
    ):
        if credential_probe is None:
            return {
                "ok": False,
                "state":
                    "blocked_credential",
                "reason":
                    "credential_probe_missing",
                "sequence":
                    build_sequence(),
            }

        credential_result = (
            credential_probe(
                {
                    "title":
                        config.get(
                            "title"
                        ),
                    "game":
                        config.get(
                            "game"
                        ),
                    "audience_type":
                        config.get(
                            "audience_type"
                        ),
                }
            )
        )

        if not credential_result.get(
            "ready"
        ):
            _STATE.update(
                {
                    "state":
                        "blocked_credential",
                    "last_error":
                        "credential_not_ready",
                }
            )

            return {
                "ok": False,
                "state":
                    "blocked_credential",
                "credential":
                    credential_result,
                "sequence":
                    build_sequence(),
            }

        _STATE[
            "credential_ready"
        ] = True

    output_result = (
        output_probe(
            {
                "video_encoder":
                    config.get(
                        "video_encoder"
                    ),
                "rtmp_sink":
                    config.get(
                        "rtmp_sink"
                    ),
                "video_bitrate":
                    config.get(
                        "video_bitrate"
                    ),
            }
        )
    )

    if not output_result.get(
        "ready"
    ):
        _STATE.update(
            {
                "state":
                    "blocked_output",
                "last_error":
                    "output_not_ready",
            }
        )

        return {
            "ok": False,
            "state":
                "blocked_output",
            "output":
                output_result,
            "sequence":
                build_sequence(),
        }

    _STATE.update(
        {
            "state":
                "ready",
            "message":
                "Sequencia validada em modo simulado.",
            "output_ready":
                True,
            "last_error":
                "",
        }
    )

    return {
        "ok": True,
        "state": "ready",
        "monitor":
            monitor_result,
        "credential":
            credential_result,
        "output":
            output_result,
        "sequence":
            build_sequence(),
    }


def reset_simulation() -> dict[str, Any]:
    _STATE.update(
        {
            "state": "stopped",
            "message": "",
            "monitor_auto": True,
            "monitor_ready": False,
            "output_ready": False,
            "credential_ready": False,
            "last_error": "",
        }
    )

    return status()
