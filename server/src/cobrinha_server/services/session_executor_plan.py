from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from cobrinha_server.core.settings import (
    GODOT_TERRAIN_EDITOR_FILE,
    PROJECT_DIR,
)


GAME_DIR = Path(
    os.getenv(
        "SNAKE_REYERS_GAME_SOURCE",
        str(PROJECT_DIR / "game-source-unavailable"),
    )
)

SERVER_DIR = PROJECT_DIR
INSTALL_DIR = SERVER_DIR.parent

EXPORTED_GAME_DIR = (
    INSTALL_DIR
    / "game"
    / ("windows" if os.name == "nt" else "linux")
)

EXPORTED_GAME_EXECUTABLE = (
    EXPORTED_GAME_DIR
    / (
        "SnakeReyers.exe"
        if os.name == "nt"
        else "SnakeReyers.x86_64"
    )
)

TERRAIN_EDITOR_FILE = GODOT_TERRAIN_EDITOR_FILE

GAME_WINDOW_WIDTH = 720
GAME_WINDOW_HEIGHT = 1280

SESSION_PREFIX = "cobrinha_session_"


def sanitize_session_id(
    value: str,
) -> str:
    text = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "_",
        str(value or "").strip(),
    ).strip("_")

    if not text:
        raise ValueError(
            "session_id_empty"
        )

    return text[:64]


@dataclass(
    frozen=True,
)
class SessionIdentity:
    session_id: str
    namespace: str


def build_identity(
    session_id: str,
) -> SessionIdentity:
    clean = sanitize_session_id(
        session_id
    )

    return SessionIdentity(
        session_id=clean,
        namespace=(
            SESSION_PREFIX
            + clean
        ),
    )


@dataclass(
    frozen=True,
)
class GameLaunchPlan:
    cwd: str
    argv: tuple[str, ...]
    environment: dict[str, str]
    width: int
    height: int


def _looks_like_godot_editor(
    executable: str,
) -> bool:
    return (
        "godot"
        in Path(
            executable
        ).name.casefold()
    )


def preferred_live_executable(
    executable: object = "",
    game_runtime: object = "build",
) -> str:
    configured = str(
        executable
        or ""
    ).strip()

    runtime = str(
        game_runtime
        or "build"
    ).strip().casefold()

    if os.name == "nt":
        return str(
            EXPORTED_GAME_EXECUTABLE
        )

    if runtime in {
        "editor",
        "godot",
        "project",
        "projeto",
    }:
        if (
            configured
            and _looks_like_godot_editor(
                configured
            )
        ):
            return configured
        return "/snap/bin/godot-4"

    if EXPORTED_GAME_EXECUTABLE.exists():
        return str(
            EXPORTED_GAME_EXECUTABLE
        )

    if configured:
        return configured

    return "/snap/bin/godot-4"


def _editor_argv(
    executable: str,
) -> tuple[str, ...]:
    return (
        executable,
        "--path",
        str(GAME_DIR),
        "--scene",
        "res://scenes/main.tscn",
        "--windowed",
        "--resolution",
        f"{GAME_WINDOW_WIDTH}x{GAME_WINDOW_HEIGHT}",
        "--single-window",
        "--",
        "--cobrinha-live",
    )


def _exported_argv(
    executable: str,
) -> tuple[str, ...]:
    return (
        executable,
        "--windowed",
        "--resolution",
        f"{GAME_WINDOW_WIDTH}x{GAME_WINDOW_HEIGHT}",
        "--single-window",
        "--",
        "--cobrinha-live",
    )


def build_game_plan(
    *,
    session_id: str,
    executable: str,
    server_url: str,
    display_value: str,
) -> GameLaunchPlan:
    identity = build_identity(
        session_id
    )

    executable = str(
        executable
        or ""
    ).strip()

    if not executable:
        raise ValueError(
            "game_executable_empty"
        )

    server_url = str(
        server_url
        or ""
    ).strip()

    if not server_url:
        raise ValueError(
            "server_url_empty"
        )

    display_value = str(
        display_value
        or ""
    ).strip()

    environment = {
        "COBRINHA_LIVE_SERVER_URL": server_url,
        "COBRINHA_SESSION_ID": identity.session_id,
        "COBRINHA_NAMESPACE": identity.namespace,
        "COBRINHA_TERRAIN_EDITOR_FILE": str(
            TERRAIN_EDITOR_FILE
        ),
    }

    if display_value:
        environment["DISPLAY"] = display_value

    executable_path = Path(
        executable
    ).expanduser()

    if _looks_like_godot_editor(
        executable
    ):
        cwd = GAME_DIR
        argv = _editor_argv(
            executable
        )
    else:
        cwd = (
            executable_path.parent
            if executable_path.parent
            != Path(".")
            else EXPORTED_GAME_DIR
        )
        argv = _exported_argv(
            executable
        )

    return GameLaunchPlan(
        cwd=str(
            cwd
        ),
        argv=argv,
        environment=environment,
        width=GAME_WINDOW_WIDTH,
        height=GAME_WINDOW_HEIGHT,
    )
