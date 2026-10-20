from __future__ import annotations

from dataclasses import (
    asdict,
    dataclass,
)
from pathlib import Path
import os
import re
from typing import Any

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

SESSION_PREFIX = (
    "cobrinha_session_"
)


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
    frozen=True
)
class SessionIdentity:
    session_id: str
    namespace: str
    audio_sink: str
    audio_monitor: str
    display_name: str

    def public_info(
        self,
    ) -> dict[str, str]:
        return asdict(self)


def build_identity(
    session_id: str,
) -> SessionIdentity:
    clean = sanitize_session_id(
        session_id
    )

    namespace = (
        SESSION_PREFIX
        + clean
    )

    return SessionIdentity(
        session_id=clean,
        namespace=namespace,
        audio_sink=namespace,
        audio_monitor=(
            namespace
            + ".monitor"
        ),
        display_name=(
            "cobrinha_"
            + clean
        ),
    )


@dataclass(
    frozen=True
)
class GameLaunchPlan:
    cwd: str
    argv: tuple[str, ...]
    environment: dict[str, str]
    width: int
    height: int

    def public_info(
        self,
    ) -> dict[str, Any]:
        return {
            "cwd": self.cwd,
            "argv": list(
                self.argv
            ),
            "environment": dict(
                self.environment
            ),
            "width": self.width,
            "height": self.height,
        }


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
        "--screen",
        "1",
        "--windowed",
        "--resolution",
        f"{GAME_WINDOW_WIDTH}x{GAME_WINDOW_HEIGHT}",
        "--single-window",
        "--audio-driver",
        "PulseAudio",
        "--",
        "--cobrinha-live",
    )


def _exported_argv(
    executable: str,
) -> tuple[str, ...]:
    if os.name == "nt":
        return (
            executable,
            "--windowed",
            "--resolution",
            f"{GAME_WINDOW_WIDTH}x{GAME_WINDOW_HEIGHT}",
            "--single-window",
            "--",
            "--cobrinha-live",
        )

    return (
        executable,
        "--screen",
        "1",
        "--windowed",
        "--resolution",
        f"{GAME_WINDOW_WIDTH}x{GAME_WINDOW_HEIGHT}",
        "--single-window",
        "--display-driver",
        "x11",
        "--audio-driver",
        "PulseAudio",
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
        "COBRINHA_LIVE_SERVER_URL":
            server_url,
        "COBRINHA_SESSION_ID":
            identity.session_id,
        "COBRINHA_NAMESPACE":
            identity.namespace,
        "COBRINHA_TERRAIN_EDITOR_FILE":
            str(TERRAIN_EDITOR_FILE),
    }

    if os.name != "nt":
        environment.update(
            {
                "PULSE_SINK": identity.audio_sink,
                "SDL_AUDIODRIVER": "pulse",
                "PIPEWIRE_LATENCY": "256/48000",
                "PULSE_PROP": (
                    "application.name=CobrinhaLive "
                    "application.id=cobrinha_live "
                    "media.name=CobrinhaLive"
                ),
                "DRI_PRIME": "1",
                "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
                "__NV_PRIME_RENDER_OFFLOAD": "1",
                "__VK_LAYER_NV_optimus": "NVIDIA_only",
            }
        )

    if display_value:
        environment[
            "DISPLAY"
        ] = display_value

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


@dataclass(
    frozen=True
)
class OwnershipRecord:
    role: str
    pid: int
    session_id: str
    expected_cwd: str
    required_markers: tuple[str, ...]

    def public_info(
        self,
    ) -> dict[str, Any]:
        return {
            "role": self.role,
            "pid": self.pid,
            "session_id":
                self.session_id,
            "expected_cwd":
                self.expected_cwd,
            "required_markers":
                list(
                    self.required_markers
                ),
        }


def ownership_matches(
    record: OwnershipRecord,
    *,
    actual_cwd: str,
    actual_command: str,
) -> bool:
    if int(
        record.pid
    ) <= 1:
        return False

    if (
        record.expected_cwd
        and Path(
            actual_cwd
        ) != Path(
            record.expected_cwd
        )
    ):
        return False

    command = str(
        actual_command
        or ""
    )

    for marker in (
        record.required_markers
    ):
        if marker not in command:
            return False

    return True


def game_ownership_record(
    *,
    pid: int,
    session_id: str,
) -> OwnershipRecord:
    identity = build_identity(
        session_id
    )

    return OwnershipRecord(
        role="game",
        pid=int(pid),
        session_id=
            identity.session_id,
        expected_cwd="",
        required_markers=(
            "--cobrinha-live",
        ),
    )


def validate_singletons(
    *,
    server_count: int,
    game_count: int,
    capture_count: int,
    display_count: int,
    sink_count: int,
    monitor_count: int,
) -> dict[str, Any]:
    counts = {
        "server":
            int(server_count),
        "game":
            int(game_count),
        "capture":
            int(capture_count),
        "display":
            int(display_count),
        "sink":
            int(sink_count),
        "monitor":
            int(monitor_count),
    }

    expected = {
        "server": 1,
        "game": 1,
        "capture": 1,
        "display": 0,
        "sink": 1,
        "monitor": 1,
    }

    mismatches = {
        key: {
            "expected":
                expected[key],
            "actual":
                value,
        }
        for key, value
        in counts.items()
        if value != expected[key]
    }

    return {
        "ok":
            not mismatches,
        "counts":
            counts,
        "mismatches":
            mismatches,
    }


def planned_sequence() -> tuple[
    str,
    ...
]:
    return (
        "validate_private_config",
        "create_session_identity",
        "verify_no_foreign_runtime",
        "prepare_isolated_audio",
        "use_native_godot_display",
        "launch_game",
        "wait_game_bridge",
        "prepare_monitor",
        "wait_monitor",
        "prepare_destination",
        "launch_capture",
        "wait_initial_ack",
        "mark_running",
    )
