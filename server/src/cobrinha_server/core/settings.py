from __future__ import annotations

import os
from pathlib import Path


_PACKAGE_PROJECT_DIR = Path(__file__).resolve().parents[3]

PROJECT_DIR = Path(
    os.getenv(
        "COBRINHA_SERVER_DIR",
        str(_PACKAGE_PROJECT_DIR),
    )
).resolve()

RUNS_DIR = PROJECT_DIR / "runs"
LOGS_DIR = RUNS_DIR / "logs"
PRIVATE_DIR = PROJECT_DIR / "private"
ASSETS_DIR = PROJECT_DIR / "assets"
CONFIG_DIR = PROJECT_DIR / "config"
VOICE_DIR = ASSETS_DIR / "voice"
BUILDS_DIR = PROJECT_DIR / "builds"

TIKTOK_MONITOR_DIR = (
    PROJECT_DIR
    / "external"
    / "tiktok-live-monitoring-server"
)
TIKTOK_MONITOR_ENTRY = (
    TIKTOK_MONITOR_DIR
    / "server.js"
)
TIKTOK_MONITOR_PACKAGE = (
    TIKTOK_MONITOR_DIR
    / "package.json"
)
TIKTOK_MONITOR_PID_FILE = (
    RUNS_DIR
    / "tiktok-live-monitor.pid"
)
TIKTOK_MONITOR_LOG_FILE = (
    LOGS_DIR
    / "tiktok-live-monitor.log"
)
TIKTOK_MONITOR_HOST = os.getenv(
    "COBRINHA_TIKTOK_MONITOR_HOST",
    "127.0.0.1",
)
TIKTOK_MONITOR_PORT = int(
    os.getenv(
        "COBRINHA_TIKTOK_MONITOR_PORT",
        "2619",
    )
)
SOCIAL_TEXT_AI_CONFIG_FILE = (
    PRIVATE_DIR
    / "social_text_ai.json"
)
BLACKLIST_FILE = (
    PRIVATE_DIR
    / "chat_blacklist_terms.txt"
)
GODOT_TERRAIN_EDITOR_FILE = (
    PRIVATE_DIR
    / "cobrinha_terrain_editor.json"
)
TEXTURE_LIBRARY_DIR = (
    PRIVATE_DIR
    / "textures"
)
TEXTURE_MANIFEST_FILE = (
    PRIVATE_DIR
    / "terrain_textures.json"
)

SESSION_CONTROL_CONFIG_FILE = (
    PRIVATE_DIR
    / "live_control.json"
)

PIPER_VOICE_DIR = Path(
    os.getenv(
        "COBRINHA_PIPER_VOICE_DIR",
        str(VOICE_DIR / "piper"),
    )
).expanduser()

DEFAULT_PIPER_VOICE = Path(
    os.getenv(
        "COBRINHA_PIPER_VOICE",
        str(PIPER_VOICE_DIR / "pt_BR-faber-medium.onnx"),
    )
).expanduser()

DEFAULT_HOST = os.getenv(
    "COBRINHA_SERVER_HOST",
    "127.0.0.1",
)
DEFAULT_PORT = int(
    os.getenv(
        "COBRINHA_SERVER_PORT",
        "9393",
    )
)


def application_version() -> str:
    version_file = PROJECT_DIR.parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def ensure_runtime_dirs() -> None:
    for path in (
        RUNS_DIR,
        LOGS_DIR,
        PRIVATE_DIR,
        ASSETS_DIR,
        VOICE_DIR,
        PIPER_VOICE_DIR,
        BUILDS_DIR,
        TEXTURE_LIBRARY_DIR,
        ASSETS_DIR / "music" / "background",
    ):
        path.mkdir(
            parents=True,
            exist_ok=True,
        )
