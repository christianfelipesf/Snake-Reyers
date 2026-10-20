from __future__ import annotations

import time
from typing import Any

from cobrinha_server.bridge.godot_bridge import (
    godot_bridge,
)
from cobrinha_server.services import (
    game_launcher,
    tiktok_monitor,
)
from cobrinha_server.services.speech_dispatcher import (
    dispatcher_running,
)
from cobrinha_server.services.speech_queue import (
    status as speech_queue_status,
)


GODOT_STALE_WARNING_SECONDS = 20.0
GODOT_STALE_CRITICAL_SECONDS = 45.0
SPEECH_BACKLOG_WARNING_SIZE = 15


def _issue(
    code: str,
    message: str,
    *,
    level: str = "warning",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "level": level,
        "detail": detail or {},
    }


def status() -> dict[str, Any]:
    now = time.time()

    game = game_launcher.status()
    godot = godot_bridge.status()
    monitor = tiktok_monitor.status()
    queue = speech_queue_status()
    dispatcher = bool(
        dispatcher_running()
    )

    game_running = bool(
        game.get("running")
    )
    godot_connected = bool(
        godot.get("connected")
    )
    monitor_running = bool(
        monitor.get("running")
    )
    monitor_connected = bool(
        monitor.get("connected")
    )
    monitor_listening = bool(
        monitor.get("listening")
    )

    active = bool(
        game_running
        or godot_connected
        or monitor_running
    )

    issues: list[dict[str, Any]] = []

    if active and not game_running:
        issues.append(
            _issue(
                "game_not_running",
                "O jogo nao esta aberto.",
                detail={
                    "state":
                        str(
                            game.get("state")
                            or ""
                        ),
                },
            )
        )

    if active and not godot_connected:
        last_seen = float(
            godot.get("last_message_at")
            or 0.0
        )
        age = (
            max(0.0, now - last_seen)
            if last_seen > 0
            else 0.0
        )

        if age >= GODOT_STALE_CRITICAL_SECONDS:
            issues.append(
                _issue(
                    "godot_stale",
                    "O Godot parou de enviar sinais.",
                    level="critical",
                    detail={"seconds": round(age, 1)},
                )
            )
        elif age >= GODOT_STALE_WARNING_SECONDS:
            issues.append(
                _issue(
                    "godot_stale",
                    "O Godot esta sem sinais recentes.",
                    detail={"seconds": round(age, 1)},
                )
            )
        else:
            issues.append(
                _issue(
                    "godot_disconnected",
                    "O Godot ainda nao se conectou.",
                )
            )

    if active and not monitor_running:
        issues.append(
            _issue(
                "monitor_stopped",
                "O monitor TikTok esta parado.",
            )
        )
    elif active and not monitor_connected:
        issues.append(
            _issue(
                "monitor_connecting",
                "O monitor TikTok esta sem conexao.",
            )
        )
    elif active and not monitor_listening:
        issues.append(
            _issue(
                "monitor_waiting",
                "O monitor TikTok aguarda a live iniciar.",
            )
        )

    if active and not dispatcher:
        issues.append(
            _issue(
                "speech_dispatcher_stopped",
                "O distribuidor de fala esta parado.",
                level="critical",
            )
        )

    backlog = int(
        queue.get("pending_size")
        or 0
    ) + int(
        queue.get("ready_size")
        or 0
    )

    if backlog >= SPEECH_BACKLOG_WARNING_SIZE:
        issues.append(
            _issue(
                "speech_backlog",
                "A fila de fala esta acumulando.",
                detail={"size": backlog},
            )
        )

    if not active:
        overall = "idle"
    elif any(
        issue.get("level") == "critical"
        for issue in issues
    ):
        overall = "critical"
    elif issues:
        overall = "warning"
    else:
        overall = "ok"

    return {
        "status": overall,
        "healthy": overall in {
            "ok",
            "idle",
        },
        "active": active,
        "checked_at": now,
        "issues": issues,
        "actions": [],
        "components": {
            "game": {
                "running": game_running,
                "state": str(
                    game.get("state")
                    or ""
                ),
                "pid": int(
                    game.get("pid")
                    or 0
                ),
            },
            "godot": {
                "connected": godot_connected,
                "last_message_at": float(
                    godot.get("last_message_at")
                    or 0.0
                ),
            },
            "monitor": {
                "running": monitor_running,
                "connected": monitor_connected,
                "listening": monitor_listening,
                "rate_limited": bool(
                    monitor.get("rate_limited")
                ),
            },
            "speech": {
                "dispatcher_running": dispatcher,
                "pending": int(
                    queue.get("pending_size")
                    or 0
                ),
                "ready": int(
                    queue.get("ready_size")
                    or 0
                ),
                "active": bool(
                    queue.get("active")
                ),
            },
        },
    }
