from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from cobrinha_server.bridge.godot_bridge import (
    godot_bridge,
)
from cobrinha_server.core.settings import (
    LOGS_DIR,
)
from cobrinha_server.services import (
    music_runtime,
    tiktok_monitor,
    windows_desktop_session,
)
from cobrinha_server.services.session_executor_plan import (
    build_game_plan,
    preferred_live_executable,
)


_LOCK = threading.RLock()
_PROCESS: subprocess.Popen[bytes] | None = None
_STATE: dict[str, Any] = {
    "state": "stopped",
    "pid": 0,
    "started_at": 0.0,
    "last_error": "",
    "returncode": None,
}


def _refresh_locked() -> None:
    global _PROCESS

    if _PROCESS is None:
        _STATE["state"] = "stopped"
        _STATE["returncode"] = None
        return

    returncode = _PROCESS.poll()

    if returncode is None:
        _STATE["state"] = "running"
        _STATE["returncode"] = None
        return

    _STATE["state"] = "stopped"
    _STATE["returncode"] = int(returncode)
    _STATE["pid"] = 0
    _PROCESS = None


def status() -> dict[str, Any]:
    if os.name == "nt":
        state = windows_desktop_session.status()
        state["platform_mode"] = "windows_desktop"
        return state

    with _LOCK:
        _refresh_locked()
        running = bool(
            _PROCESS is not None
            and _PROCESS.poll() is None
        )
        return {
            **_STATE,
            "available": True,
            "running": running,
            "platform_mode": "linux_process",
            "godot": godot_bridge.status(),
        }


def _start_linux(
    config: dict[str, Any],
) -> dict[str, Any]:
    global _PROCESS

    with _LOCK:
        _refresh_locked()

        if _PROCESS is not None and _PROCESS.poll() is None:
            return {
                "ok": True,
                "state": "running",
                "already_running": True,
                "message": "O jogo ja esta aberto.",
                "game": status(),
            }

        executable = Path(
            preferred_live_executable(
                config.get("godot_executable"),
                config.get("game_runtime"),
            )
        ).expanduser()

        if not executable.is_file():
            return {
                "ok": False,
                "state": "game_not_found",
                "message": (
                    "Executavel do jogo nao encontrado: "
                    f"{executable}"
                ),
            }

        plan = build_game_plan(
            session_id="panel",
            executable=str(executable),
            server_url="http://127.0.0.1:9393",
            display_value=str(
                config.get("display")
                or os.getenv("DISPLAY", "")
            ),
        )

        log_path = LOGS_DIR / "linux-game.log"
        log_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        environment = os.environ.copy()
        environment.update(plan.environment)

        try:
            with log_path.open("ab", buffering=0) as log_file:
                _PROCESS = subprocess.Popen(
                    list(plan.argv),
                    cwd=plan.cwd,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except Exception as exc:
            _PROCESS = None
            _STATE.update(
                {
                    "state": "error",
                    "pid": 0,
                    "last_error":
                        f"{type(exc).__name__}: {exc}",
                }
            )
            return {
                "ok": False,
                "state": "error",
                "message": "Nao foi possivel abrir o jogo.",
                "error": _STATE["last_error"],
            }

        _STATE.update(
            {
                "state": "starting",
                "pid": int(_PROCESS.pid),
                "started_at": time.time(),
                "last_error": "",
                "returncode": None,
            }
        )

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        with _LOCK:
            if _PROCESS is None or _PROCESS.poll() is not None:
                break
        if godot_bridge.status().get("connected"):
            break
        time.sleep(0.25)

    clean_username = str(
        config.get("username")
        or ""
    ).strip().lstrip("@")

    monitor_state: dict[str, Any] = tiktok_monitor.status()

    if clean_username:
        monitor_state = tiktok_monitor.start_monitor(
            clean_username,
            server_url=str(
                config.get("monitor_server")
                or ""
            ),
            prepare_local_node=True,
        )

    with _LOCK:
        _refresh_locked()
        running = bool(
            _PROCESS is not None
            and _PROCESS.poll() is None
        )
        _STATE["state"] = "running" if running else "stopped"

    return {
        "ok": running,
        "execution": running,
        "state": (
            "running"
            if running
            else "game_closed_during_start"
        ),
        "message": (
            "Jogo aberto."
            if running
            else "O jogo fechou durante a inicializacao."
        ),
        "monitor": monitor_state,
        "monitor_configured": bool(clean_username),
        "game": status(),
    }


def start(
    config: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(config, dict):
        config = {}

    music_runtime.choose_session_start_track()

    if os.name == "nt":
        result = windows_desktop_session.start(
            executable=preferred_live_executable(
                config.get("godot_executable"),
                config.get("game_runtime"),
            ),
            server_url="http://127.0.0.1:9393",
            username=str(
                config.get("username")
                or ""
            ),
            monitor_server=str(
                config.get("monitor_server")
                or ""
            ),
        )
        result["game"] = status()
        return result

    return _start_linux(config)


def _stop_linux() -> dict[str, Any]:
    global _PROCESS

    with _LOCK:
        process = _PROCESS

        if process is None or process.poll() is not None:
            _refresh_locked()
            monitor_state = tiktok_monitor.stop_monitor(
                stop_local_node_runtime=True,
            )
            return {
                "ok": True,
                "state": "already_stopped",
                "message": "O jogo ja esta fechado.",
                "monitor": monitor_state,
                "game": status(),
            }

        try:
            os.killpg(
                os.getpgid(process.pid),
                signal.SIGTERM,
            )
        except (OSError, ProcessLookupError):
            process.terminate()

        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(
                    os.getpgid(process.pid),
                    signal.SIGKILL,
                )
            except (OSError, ProcessLookupError):
                process.kill()
            process.wait(timeout=5.0)

    monitor_state = tiktok_monitor.stop_monitor(
        stop_local_node_runtime=True,
    )

    with _LOCK:
        _refresh_locked()

    return {
        "ok": True,
        "state": "stopped",
        "message": "Jogo fechado.",
        "monitor": monitor_state,
        "game": status(),
    }


def stop() -> dict[str, Any]:
    if os.name == "nt":
        result = windows_desktop_session.stop()
        result["game"] = status()
        return result

    return _stop_linux()
