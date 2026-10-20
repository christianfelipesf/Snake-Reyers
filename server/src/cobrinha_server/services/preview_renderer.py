from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from cobrinha_server.core.settings import (
    DEFAULT_PORT,
    GODOT_TERRAIN_EDITOR_FILE,
    LOGS_DIR,
    PROJECT_DIR,
)
from cobrinha_server.services.session_executor_plan import (
    EXPORTED_GAME_DIR,
    EXPORTED_GAME_EXECUTABLE,
)


GAME_DIR = Path(
    os.getenv(
        "SNAKE_REYERS_GAME_SOURCE",
        str(PROJECT_DIR / "game-source-unavailable"),
    )
)

GODOT_BIN = Path(
    os.getenv(
        "GODOT_BIN",
        shutil.which("godot-4")
        or shutil.which("godot")
        or "godot-unavailable",
    )
)

_PREVIEW_PROCESS: subprocess.Popen[bytes] | None = None
_PREVIEW_LOG_HANDLE: Any | None = None
_PREVIEW_STARTED_AT: float = 0.0
_TERRAIN_EDITOR_PROCESS: subprocess.Popen[bytes] | None = None
_TERRAIN_EDITOR_LOG_HANDLE: Any | None = None
_TERRAIN_EDITOR_STARTED_AT: float = 0.0
_TERRAIN_EDITOR_COMMAND: list[str] = []
_TERRAIN_EDITOR_CWD: str = ""
_TERRAIN_EDITOR_RUNTIME: str = ""
_LOCK = threading.RLock()


def _graphical_environment() -> dict[str, str]:
    env = os.environ.copy()

    if os.name == "nt":
        return env

    uid = os.getuid()

    if not str(env.get("DISPLAY") or "").strip():
        env["DISPLAY"] = ":0"

    if not str(env.get("XDG_RUNTIME_DIR") or "").strip():
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"

    if not str(env.get("XAUTHORITY") or "").strip():
        candidates = (
            Path(f"/run/user/{uid}/gdm/Xauthority"),
            Path.home() / ".Xauthority",
        )
        selected = next(
            (path for path in candidates if path.is_file()),
            candidates[0],
        )
        env["XAUTHORITY"] = str(selected)

    return env


def _compiled_game_command(
    *,
    position: str,
    resolution: str,
    mode: str,
) -> list[str]:
    command = [
        str(EXPORTED_GAME_EXECUTABLE),
        "--windowed",
        "--position",
        position,
        "--resolution",
        resolution,
    ]

    if os.name != "nt":
        command.extend(
            [
                "--display-driver",
                "x11",
                "--audio-driver",
                "PulseAudio",
            ]
        )

    command.extend(["--", mode])
    return command


def _ensure_process_started(
    process: subprocess.Popen[bytes],
    *,
    role: str,
    log_path: Path,
) -> None:
    try:
        return_code = process.wait(timeout=0.35)
    except subprocess.TimeoutExpired:
        return

    raise RuntimeError(
        f"{role}_exited_early:{return_code}; "
        f"log={log_path}"
    )


def _refresh_process() -> None:
    global _PREVIEW_PROCESS
    global _PREVIEW_LOG_HANDLE
    global _PREVIEW_STARTED_AT
    global _TERRAIN_EDITOR_PROCESS
    global _TERRAIN_EDITOR_LOG_HANDLE
    global _TERRAIN_EDITOR_STARTED_AT
    global _TERRAIN_EDITOR_COMMAND
    global _TERRAIN_EDITOR_CWD
    global _TERRAIN_EDITOR_RUNTIME

    if _PREVIEW_PROCESS is None:
        pass
    elif _PREVIEW_PROCESS.poll() is not None:
        _PREVIEW_PROCESS = None
        _PREVIEW_STARTED_AT = 0.0

        if _PREVIEW_LOG_HANDLE is not None:
            try:
                _PREVIEW_LOG_HANDLE.close()
            except Exception:
                pass

        _PREVIEW_LOG_HANDLE = None

    if _TERRAIN_EDITOR_PROCESS is None:
        return

    if _TERRAIN_EDITOR_PROCESS.poll() is None:
        return

    _TERRAIN_EDITOR_PROCESS = None
    _TERRAIN_EDITOR_STARTED_AT = 0.0
    _TERRAIN_EDITOR_COMMAND = []
    _TERRAIN_EDITOR_CWD = ""
    _TERRAIN_EDITOR_RUNTIME = ""

    if _TERRAIN_EDITOR_LOG_HANDLE is not None:
        try:
            _TERRAIN_EDITOR_LOG_HANDLE.close()
        except Exception:
            pass

    _TERRAIN_EDITOR_LOG_HANDLE = None


def preview_status() -> dict[str, Any]:
    with _LOCK:
        _refresh_process()

        process = _PREVIEW_PROCESS

        return {
            "running": bool(
                process is not None
                and process.poll() is None
            ),
            "pid": (
                int(process.pid)
                if process is not None
                and process.poll() is None
                else None
            ),
            "started_at":
                _PREVIEW_STARTED_AT,
            "game_dir":
                str(GAME_DIR),
        }


def terrain_editor_status() -> dict[str, Any]:
    with _LOCK:
        _refresh_process()

        process = _TERRAIN_EDITOR_PROCESS

        return {
            "running": bool(
                process is not None
                and process.poll() is None
            ),
            "pid": (
                int(process.pid)
                if process is not None
                and process.poll() is None
                else None
            ),
            "started_at":
                _TERRAIN_EDITOR_STARTED_AT,
            "game_dir":
                str(GAME_DIR),
            "runtime":
                _TERRAIN_EDITOR_RUNTIME,
            "cwd":
                _TERRAIN_EDITOR_CWD,
            "command":
                list(_TERRAIN_EDITOR_COMMAND),
        }


def _terrain_editor_launch_plan() -> tuple[list[str], str, str]:
    if EXPORTED_GAME_EXECUTABLE.is_file():
        return (
            _compiled_game_command(
                position="760,70",
                resolution="960x720",
                mode="--cobrinha-terrain-editor",
            ),
            str(EXPORTED_GAME_DIR),
            "build",
        )

    if not GODOT_BIN.is_file():
        raise FileNotFoundError(
            f"Godot nao encontrado: {GODOT_BIN}"
        )

    if not GAME_DIR.is_dir():
        raise FileNotFoundError(
            f"Projeto nao encontrado: {GAME_DIR}"
        )

    return (
        [
            str(GODOT_BIN),
            "--path",
            str(GAME_DIR),
            "--scene",
            "res://scenes/main.tscn",
            "--position",
            "760,70",
            "--resolution",
            "960x720",
            "--",
            "--cobrinha-terrain-editor",
        ],
        str(GAME_DIR),
        "debug",
    )


def start_preview() -> dict[str, Any]:
    global _PREVIEW_PROCESS
    global _PREVIEW_LOG_HANDLE
    global _PREVIEW_STARTED_AT

    with _LOCK:
        _refresh_process()

        if (
            _PREVIEW_PROCESS is not None
            and _PREVIEW_PROCESS.poll() is None
        ):
            return {
                "ok": True,
                "already_running": True,
                **preview_status(),
            }

        using_compiled_game = (
            EXPORTED_GAME_EXECUTABLE.is_file()
        )

        if not using_compiled_game:
            if not GODOT_BIN.is_file():
                raise FileNotFoundError(
                    "Build do jogo nao encontrada."
                )

            if not GAME_DIR.is_dir():
                raise FileNotFoundError(
                    "Projeto do jogo nao disponivel."
                )

        LOGS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        log_path = (
            LOGS_DIR
            / "preview_godot.log"
        )

        env = _graphical_environment()
        env[
            "COBRINHA_LIVE_SERVER_URL"
        ] = (
            f"ws://127.0.0.1:"
            f"{DEFAULT_PORT}"
            "/ws/godot-preview"
        )
        env[
            "COBRINHA_TERRAIN_EDITOR_FILE"
        ] = str(
            GODOT_TERRAIN_EDITOR_FILE
        )

        if using_compiled_game:
            command = _compiled_game_command(
                position="980,90",
                resolution="540x960",
                mode="--cobrinha-preview",
            )
            process_cwd = EXPORTED_GAME_DIR
        else:
            command = [
                str(GODOT_BIN),
                "--path",
                str(GAME_DIR),
                "--scene",
                "res://scenes/main.tscn",
                "--position",
                "980,90",
                "--resolution",
                "540x960",
                "--",
                "--cobrinha-preview",
            ]
            process_cwd = GAME_DIR

        _PREVIEW_LOG_HANDLE = open(
            log_path,
            "ab",
            buffering=0,
        )

        try:
            _PREVIEW_PROCESS = (
                subprocess.Popen(
                    command,
                    cwd=str(process_cwd),
                    env=env,
                    stdout=_PREVIEW_LOG_HANDLE,
                    stderr=subprocess.STDOUT,
                )
            )
            _ensure_process_started(
                _PREVIEW_PROCESS,
                role="preview",
                log_path=log_path,
            )
        except Exception:
            _PREVIEW_LOG_HANDLE.close()
            _PREVIEW_LOG_HANDLE = None
            _PREVIEW_PROCESS = None
            raise

        _PREVIEW_STARTED_AT = time.time()

        return {
            "ok": True,
            "already_running": False,
            **preview_status(),
        }


def start_terrain_editor() -> dict[str, Any]:
    global _TERRAIN_EDITOR_PROCESS
    global _TERRAIN_EDITOR_LOG_HANDLE
    global _TERRAIN_EDITOR_STARTED_AT
    global _TERRAIN_EDITOR_COMMAND
    global _TERRAIN_EDITOR_CWD
    global _TERRAIN_EDITOR_RUNTIME

    with _LOCK:
        _refresh_process()

        if (
            _TERRAIN_EDITOR_PROCESS is not None
            and _TERRAIN_EDITOR_PROCESS.poll() is None
        ):
            return {
                "ok": True,
                "already_running": True,
                **terrain_editor_status(),
            }

        LOGS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        log_path = (
            LOGS_DIR
            / "terrain_editor_godot.log"
        )

        env = _graphical_environment()
        env[
            "COBRINHA_TERRAIN_EDITOR_FILE"
        ] = str(
            GODOT_TERRAIN_EDITOR_FILE
        )

        command, cwd, runtime = _terrain_editor_launch_plan()

        _TERRAIN_EDITOR_LOG_HANDLE = open(
            log_path,
            "ab",
            buffering=0,
        )

        try:
            _TERRAIN_EDITOR_PROCESS = (
                subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=_TERRAIN_EDITOR_LOG_HANDLE,
                    stderr=subprocess.STDOUT,
                )
            )
            _ensure_process_started(
                _TERRAIN_EDITOR_PROCESS,
                role="terrain_editor",
                log_path=log_path,
            )
        except Exception:
            _TERRAIN_EDITOR_LOG_HANDLE.close()
            _TERRAIN_EDITOR_LOG_HANDLE = None
            _TERRAIN_EDITOR_PROCESS = None
            raise

        _TERRAIN_EDITOR_STARTED_AT = time.time()
        _TERRAIN_EDITOR_COMMAND = list(command)
        _TERRAIN_EDITOR_CWD = str(cwd)
        _TERRAIN_EDITOR_RUNTIME = str(runtime)

        return {
            "ok": True,
            "already_running": False,
            **terrain_editor_status(),
        }
