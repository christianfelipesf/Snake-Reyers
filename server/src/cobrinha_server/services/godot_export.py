from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from cobrinha_server.core.json_store import (
    read_json,
    write_json_atomic,
)
from cobrinha_server.core.settings import (
    BUILDS_DIR,
    LOGS_DIR,
    PROJECT_DIR,
    RUNS_DIR,
)


GAME_DIR = Path(
    os.getenv(
        "SNAKE_REYERS_GAME_SOURCE",
        str(PROJECT_DIR / "game-source-unavailable"),
    )
)

EXPORT_PRESET_NAME = (
    "Cobrinha Linux Release"
)

BUILD_DIR = (
    BUILDS_DIR
    / "cobrinha-linux"
)

EXPORT_EXECUTABLE = (
    BUILD_DIR
    / "cobrinha_live.x86_64"
)

EXPORT_LOG_FILE = (
    LOGS_DIR
    / "godot_export.log"
)

EXPORT_STATUS_FILE = (
    RUNS_DIR
    / "godot_export_status.json"
)

EXPORT_PRESETS_FILE = (
    GAME_DIR
    / "export_presets.cfg"
)

EXPORT_TEMPLATES_DIR = (
    Path.home()
    / "snap"
    / "godot-4"
    / "current"
    / ".local"
    / "share"
    / "godot"
    / "export_templates"
    / "4.7.2.stable.mono"
)

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None


def _now() -> float:
    return time.time()


def _base_status() -> dict[str, Any]:
    templates_ready = _templates_ready()

    return {
        "ok": True,
        "state": "idle",
        "running": False,
        "preset": EXPORT_PRESET_NAME,
        "game_dir": str(
            GAME_DIR
        ),
        "build_dir": str(
            BUILD_DIR
        ),
        "executable": str(
            EXPORT_EXECUTABLE
        ),
        "executable_exists":
            EXPORT_EXECUTABLE.exists(),
        "pck_exists":
            EXPORT_EXECUTABLE.with_suffix(
                ".pck"
            ).exists(),
        "log_file": str(
            EXPORT_LOG_FILE
        ),
        "templates_dir": str(
            EXPORT_TEMPLATES_DIR
        ),
        "templates_ready":
            templates_ready,
        "updated_at": _now(),
        "message": "",
    }


def _read_status() -> dict[str, Any]:
    raw = read_json(
        EXPORT_STATUS_FILE,
        {},
    )

    if not isinstance(
        raw,
        dict,
    ):
        raw = {}

    return {
        **_base_status(),
        **raw,
        "game_dir": str(
            GAME_DIR
        ),
        "build_dir": str(
            BUILD_DIR
        ),
        "executable": str(
            EXPORT_EXECUTABLE
        ),
        "log_file": str(
            EXPORT_LOG_FILE
        ),
        "templates_dir": str(
            EXPORT_TEMPLATES_DIR
        ),
        "running":
            bool(
                _THREAD
                and _THREAD.is_alive()
            ),
        "executable_exists":
            EXPORT_EXECUTABLE.exists(),
        "pck_exists":
            EXPORT_EXECUTABLE.with_suffix(
                ".pck"
            ).exists(),
        "templates_ready":
            _templates_ready(),
    }


def _write_status(
    updates: dict[str, Any],
) -> dict[str, Any]:
    status = {
        **_read_status(),
        **updates,
        "updated_at": _now(),
        "executable_exists":
            EXPORT_EXECUTABLE.exists(),
        "pck_exists":
            EXPORT_EXECUTABLE.with_suffix(
                ".pck"
            ).exists(),
        "templates_ready":
            _templates_ready(),
    }

    write_json_atomic(
        EXPORT_STATUS_FILE,
        status,
    )

    return status


def build_status() -> dict[str, Any]:
    with _LOCK:
        return _read_status()


def _templates_ready() -> bool:
    return (
        (
            EXPORT_TEMPLATES_DIR
            / "linux_release.x86_64"
        ).exists()
        and (
            EXPORT_TEMPLATES_DIR
            / "linux_debug.x86_64"
        ).exists()
    )


def _append_export_preset() -> None:
    text = ""

    if EXPORT_PRESETS_FILE.exists():
        text = EXPORT_PRESETS_FILE.read_text(
            encoding="utf-8",
            errors="replace",
        )

    if EXPORT_PRESET_NAME in text:
        return

    existing = [
        int(match.group(1))
        for match in re.finditer(
            r"^\[preset\.(\d+)\]$",
            text,
            flags=re.MULTILINE,
        )
    ]

    index = (
        max(existing) + 1
        if existing
        else 0
    )

    block = f"""

[preset.{index}]

name="{EXPORT_PRESET_NAME}"
platform="Linux"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="{EXPORT_EXECUTABLE}"
encryption_include_filters=""
encryption_exclude_filters=""
encrypt_pck=false
encrypt_directory=false

[preset.{index}.options]

binary_format/architecture="x86_64"
binary_format/embed_pck=false
texture_format/bptc=true
texture_format/s3tc=true
texture_format/etc=false
texture_format/etc2=false
ssh_remote_deploy/enabled=false
ssh_remote_deploy/host="user@host_ip"
ssh_remote_deploy/port="22"
ssh_remote_deploy/extra_args_ssh=""
ssh_remote_deploy/extra_args_scp=""
ssh_remote_deploy/run_script="#!/usr/bin/env bash\\nexport DISPLAY=:0\\nunzip -o -q \\"{{temp_dir}}/{{archive_name}}\\" -d \\"{{temp_dir}}\\"\\n\\"{{temp_dir}}/{{exe_name}}\\" {{cmd_args}}"
ssh_remote_deploy/cleanup_script="#!/usr/bin/env bash\\nkill $(pgrep -x -f \\"{{temp_dir}}/{{exe_name}} {{cmd_args}}\\")\\nrm -rf \\"{{temp_dir}}\\""
""".lstrip()

    EXPORT_PRESETS_FILE.write_text(
        (
            text.rstrip()
            + "\n\n"
            + block
        ).lstrip(),
        encoding="utf-8",
    )


def _configured_godot_editor() -> str:
    try:
        from cobrinha_server.services.session_control import (
            public_config,
        )

        candidate = str(
            public_config().get(
                "godot_executable"
            )
            or ""
        ).strip()

    except Exception:
        candidate = ""

    if (
        candidate
        and "godot" in Path(
            candidate
        ).name.casefold()
    ):
        return candidate

    return "/snap/bin/godot-4"


def _export_environment() -> dict[str, str]:
    env = os.environ.copy()

    env.update(
        {
            "DRI_PRIME": "1",
            "__GLX_VENDOR_LIBRARY_NAME":
                "nvidia",
            "__NV_PRIME_RENDER_OFFLOAD":
                "1",
            "__VK_LAYER_NV_optimus":
                "NVIDIA_only",
        }
    )

    env.setdefault(
        "DISPLAY",
        ":0",
    )

    return env


def _run_export(
    *,
    use_for_live: bool,
) -> None:
    _write_status(
        {
            "state": "running",
            "running": True,
            "message":
                "Exportando Godot release.",
            "last_error": "",
        }
    )

    if not _templates_ready():
        _write_status(
            {
                "state": "failed",
                "running": False,
                "message": (
                    "Templates Linux do Godot "
                    "nao estao instalados."
                ),
                "last_error":
                    "godot_export_templates_missing",
            }
        )
        return

    BUILD_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    EXPORT_LOG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    editor = _configured_godot_editor()
    argv = [
        editor,
        "--headless",
        "--verbose",
        "--path",
        str(GAME_DIR),
        "--export-release",
        EXPORT_PRESET_NAME,
        str(EXPORT_EXECUTABLE),
    ]

    started = _now()

    try:
        _append_export_preset()

        with EXPORT_LOG_FILE.open(
            "ab"
        ) as log_handle:
            log_handle.write(
                (
                    "\n\n=== COBRINHA EXPORT "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
                    + " ".join(argv)
                    + "\n"
                ).encode("utf-8")
            )

            result = subprocess.run(
                argv,
                cwd=str(GAME_DIR),
                env=_export_environment(),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                check=False,
            )

        if EXPORT_EXECUTABLE.exists():
            EXPORT_EXECUTABLE.chmod(
                EXPORT_EXECUTABLE.stat().st_mode
                | 0o111
            )

        if (
            result.returncode == 0
            and EXPORT_EXECUTABLE.exists()
        ):
            if use_for_live:
                from cobrinha_server.services.session_control import (
                    save_config,
                )

                save_config(
                    {
                        "godot_executable":
                            str(
                                EXPORT_EXECUTABLE
                            )
                    }
                )

            _write_status(
                {
                    "state": "done",
                    "running": False,
                    "returncode":
                        result.returncode,
                    "duration_seconds":
                        round(
                            _now()
                            - started,
                            2,
                        ),
                    "message": (
                        "Build release gerado"
                        + (
                            " e configurado para a proxima live."
                            if use_for_live
                            else "."
                        )
                    ),
                    "used_for_live":
                        bool(use_for_live),
                    "last_error": "",
                }
            )
            return

        _write_status(
            {
                "state": "failed",
                "running": False,
                "returncode":
                    result.returncode,
                "duration_seconds":
                    round(
                        _now()
                        - started,
                        2,
                    ),
                "message":
                    "Falha ao exportar. Veja o log do build.",
                "last_error":
                    "godot_export_failed",
            }
        )

    except Exception as error:
        _write_status(
            {
                "state": "failed",
                "running": False,
                "duration_seconds":
                    round(
                        _now()
                        - started,
                        2,
                    ),
                "message":
                    "Erro interno no exportador.",
                "last_error":
                    str(error),
            }
        )


def start_export_build(
    *,
    use_for_live: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    global _THREAD

    with _LOCK:
        if (
            _THREAD
            and _THREAD.is_alive()
        ):
            return {
                **_read_status(),
                "ok": False,
                "error":
                    "build_already_running",
            }

        _THREAD = threading.Thread(
            target=_run_export,
            kwargs={
                "use_for_live":
                    bool(use_for_live),
            },
            name="cobrinha-godot-export",
            daemon=True,
        )
        _THREAD.start()

        return _read_status()
