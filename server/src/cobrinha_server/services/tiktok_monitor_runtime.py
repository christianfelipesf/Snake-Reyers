from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from cobrinha_server.core.settings import (
    TIKTOK_MONITOR_DIR,
    TIKTOK_MONITOR_ENTRY,
    TIKTOK_MONITOR_HOST,
    TIKTOK_MONITOR_PACKAGE,
    TIKTOK_MONITOR_PID_FILE,
    TIKTOK_MONITOR_PORT,
    TIKTOK_MONITOR_LOG_FILE,
    TOR_SOCKS_HOST,
    TOR_SOCKS_PORT,
)


def _windows_hidden_process_kwargs() -> dict[str, int]:
    if os.name != "nt":
        return {}
    return {
        "creationflags": int(
            getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )
        )
    }


def _binary(
    name: str,
) -> str:
    return str(
        shutil.which(name)
        or ""
    )


def tcp_listening(
    host: str,
    port: int,
    timeout: float = 0.30,
) -> bool:
    try:
        with socket.create_connection(
            (
                str(host),
                int(port),
            ),
            timeout=max(
                0.05,
                float(timeout),
            ),
        ):
            return True
    except OSError:
        return False


def tor_status() -> dict[str, Any]:
    return {
        "host": TOR_SOCKS_HOST,
        "port": TOR_SOCKS_PORT,
        "socks_listening":
            tcp_listening(
                TOR_SOCKS_HOST,
                TOR_SOCKS_PORT,
            ),
        "torsocks_binary":
            _binary("torsocks"),
    }


def node_source_status() -> dict[str, Any]:
    directory = Path(
        TIKTOK_MONITOR_DIR
    )

    entry = Path(
        TIKTOK_MONITOR_ENTRY
    )

    package = Path(
        TIKTOK_MONITOR_PACKAGE
    )

    modules = (
        directory
        / "node_modules"
    )

    return {
        "directory":
            str(directory),
        "directory_exists":
            directory.is_dir(),
        "entry":
            str(entry),
        "entry_exists":
            entry.is_file(),
        "package":
            str(package),
        "package_exists":
            package.is_file(),
        "node_modules_exists":
            modules.is_dir(),
        "node_binary":
            _binary("node"),
        "npm_binary":
            _binary("npm"),
        "torsocks_binary":
            _binary("torsocks"),
    }


def local_server_status() -> dict[str, Any]:
    process = process_status()
    listening = tcp_listening(
        TIKTOK_MONITOR_HOST,
        TIKTOK_MONITOR_PORT,
    )

    return {
        "host":
            TIKTOK_MONITOR_HOST,
        "port":
            TIKTOK_MONITOR_PORT,
        "listening":
            listening,
        "owned_by_project":
            bool(process.get("running")),
        "port_owned_by_other_process":
            bool(
                listening
                and not process.get("running")
            ),
        "process": process,
    }


def readiness() -> dict[str, Any]:
    tor = tor_status()
    node = node_source_status()
    local = local_server_status()

    source_ready = bool(
        node.get("directory_exists")
        and node.get("entry_exists")
        and node.get("package_exists")
    )

    binaries_ready = bool(
        node.get("node_binary")
    )

    dependencies_ready = bool(
        node.get("node_modules_exists")
    )

    tor_ready = bool(
        tor.get("socks_listening")
    )

    return {
        "source_ready":
            source_ready,
        "binaries_ready":
            binaries_ready,
        "dependencies_ready":
            dependencies_ready,
        "tor_ready":
            tor_ready,
        "ready_to_launch": bool(
            source_ready
            and binaries_ready
            and dependencies_ready
            and tor_ready
        ),
        "tor": tor,
        "node": node,
        "local_server": local,
        "auto_start": False,
    }


def launch_plan() -> dict[str, Any]:
    state = readiness()

    return {
        "ok": bool(
            state.get(
                "ready_to_launch"
            )
        ),
        "cwd":
            str(TIKTOK_MONITOR_DIR),
        "program":
            _binary("node")
            or "node",
        "arguments": [
            str(
                Path(
                    TIKTOK_MONITOR_ENTRY
                ).name
            ),
        ],
        "environment": {
            "SNAKE_REYERS_REQUIRE_TOR_MONITOR":
                "1",
            "SNAKE_REYERS_TOR_PROXY":
                (
                    "socks5h://"
                    + str(TOR_SOCKS_HOST)
                    + ":"
                    + str(TOR_SOCKS_PORT)
                ),
            "TIKTOK_MONITOR_PORT":
                str(
                    TIKTOK_MONITOR_PORT
                ),
        },
        "readiness": state,
        "executes": False,
    }


def _read_pid() -> int:
    path = Path(
        TIKTOK_MONITOR_PID_FILE
    )

    try:
        raw = path.read_text(
            encoding="utf-8"
        ).strip()
    except OSError:
        return 0

    try:
        pid = int(raw)
    except ValueError:
        return 0

    return (
        pid
        if pid > 1
        else 0
    )


def _pid_exists(
    pid: int,
) -> bool:
    if int(pid) <= 1:
        return False

    if os.name == "nt":
        try:
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"PID eq {int(pid)}",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=2.0,
                **_windows_hidden_process_kwargs(),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return f'"{int(pid)}"' in result.stdout

    try:
        os.kill(
            int(pid),
            0,
        )
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

    return True


def _process_cmdline(
    pid: int,
) -> str:
    if os.name == "nt":
        try:
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"PID eq {int(pid)}",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=2.0,
                **_windows_hidden_process_kwargs(),
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return result.stdout.strip()

    path = Path(
        f"/proc/{int(pid)}/cmdline"
    )

    try:
        data = path.read_bytes()
    except OSError:
        return ""

    return (
        data
        .replace(
            b"\x00",
            b" ",
        )
        .decode(
            "utf-8",
            errors="replace",
        )
        .strip()
    )


def _process_cwd(
    pid: int,
) -> str:
    if os.name == "nt":
        return str(
            Path(
                TIKTOK_MONITOR_DIR
            ).resolve()
        )

    path = Path(
        f"/proc/{int(pid)}/cwd"
    )

    try:
        return str(
            path.resolve()
        )
    except OSError:
        return ""


def pid_is_ours(
    pid: int,
) -> bool:
    if not _pid_exists(pid):
        return False

    expected_cwd = str(
        Path(
            TIKTOK_MONITOR_DIR
        ).resolve()
    )

    actual_cwd = (
        _process_cwd(pid)
    )

    if actual_cwd != expected_cwd:
        return False

    command = (
        _process_cmdline(pid)
        .casefold()
    )

    return (
        "node" in command
        and (
            os.name == "nt"
            or "server.js" in command
        )
    )


def process_status() -> dict[str, Any]:
    pid = _read_pid()

    exists = bool(
        pid
        and _pid_exists(pid)
    )

    owned = bool(
        pid
        and pid_is_ours(pid)
    )

    return {
        "pid": pid,
        "pid_exists": exists,
        "owned_by_project": owned,
        "running": bool(
            exists
            and owned
        ),
        "pid_file":
            str(
                TIKTOK_MONITOR_PID_FILE
            ),
    }


def _write_pid(
    pid: int,
) -> None:
    path = Path(
        TIKTOK_MONITOR_PID_FILE
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        f"{int(pid)}\n",
        encoding="utf-8",
    )


def _remove_pid_file() -> None:
    path = Path(
        TIKTOK_MONITOR_PID_FILE
    )

    try:
        path.unlink(
            missing_ok=True
        )
    except OSError:
        pass


def start_local_node(
    *,
    execute: bool = False,
) -> dict[str, Any]:
    state = readiness()
    process = process_status()
    local_server = state.get("local_server")
    if not isinstance(local_server, dict):
        local_server = {}

    if process.get("running"):
        return {
            "ok": True,
            "started": False,
            "already_running": True,
            "execute_requested":
                bool(execute),
            "process": process,
            "readiness": state,
        }

    if bool(
        local_server.get(
            "port_owned_by_other_process"
        )
    ):
        return {
            "ok": False,
            "started": False,
            "execute_requested":
                bool(execute),
            "reason":
                "local_port_owned_by_other_process",
            "process": process,
            "readiness": state,
            "local_server": local_server,
        }

    if not execute:
        return {
            "ok": bool(
                state.get(
                    "ready_to_launch"
                )
            ),
            "started": False,
            "execute_requested":
                False,
            "reason": "dry_run",
            "process": process,
            "readiness": state,
            "launch_plan":
                launch_plan(),
        }

    if not state.get(
        "source_ready"
    ):
        return {
            "ok": False,
            "started": False,
            "reason":
                "source_not_ready",
            "readiness": state,
        }

    if not state.get(
        "binaries_ready"
    ):
        return {
            "ok": False,
            "started": False,
            "reason":
                "binaries_not_ready",
            "readiness": state,
        }

    if not state.get(
        "dependencies_ready"
    ):
        return {
            "ok": False,
            "started": False,
            "reason":
                "dependencies_not_ready",
            "readiness": state,
        }

    if not state.get(
        "tor_ready"
    ):
        return {
            "ok": False,
            "started": False,
            "reason":
                "tor_not_ready",
            "readiness": state,
        }

    plan = launch_plan()

    log_path = Path(
        TIKTOK_MONITOR_LOG_FILE
    )

    log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    environment = os.environ.copy()

    for key, value in (
        plan.get("environment")
        or {}
    ).items():
        environment[
            str(key)
        ] = str(value)

    environment[
        "COBRINHA_TIKTOK_MONITOR_WRAPPED"
    ] = "1"

    environment[
        "COBRINHA_TIKTOK_MONITOR_DIR"
    ] = str(
        TIKTOK_MONITOR_DIR
    )

    with log_path.open(
        "ab",
        buffering=0,
    ) as log_file:
        process_obj = subprocess.Popen(
            [
                str(
                    plan["program"]
                ),
                *[
                    str(item)
                    for item in (
                        plan.get(
                            "arguments"
                        )
                        or []
                    )
                ],
            ],
            cwd=str(
                TIKTOK_MONITOR_DIR
            ),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=(
                os.name != "nt"
            ),
            **_windows_hidden_process_kwargs(),
        )

    _write_pid(
        process_obj.pid
    )

    deadline = (
        time.monotonic()
        + 6.0
    )

    listening = False

    while (
        time.monotonic()
        < deadline
    ):
        if (
            process_obj.poll()
            is not None
        ):
            break

        if tcp_listening(
            TIKTOK_MONITOR_HOST,
            TIKTOK_MONITOR_PORT,
            timeout=0.15,
        ):
            listening = True
            break

        time.sleep(0.15)

    final_process = (
        process_status()
    )

    if (
        listening
        and final_process.get(
            "running"
        )
    ):
        return {
            "ok": True,
            "started": True,
            "execute_requested":
                True,
            "process":
                final_process,
            "local_server":
                local_server_status(),
        }

    if (
        process_obj.poll()
        is not None
    ):
        _remove_pid_file()

    return {
        "ok": False,
        "started": False,
        "execute_requested":
            True,
        "reason":
            "local_node_not_listening",
        "returncode":
            process_obj.poll(),
        "process":
            process_status(),
        "local_server":
            local_server_status(),
    }


def stop_local_node(
    *,
    execute: bool = False,
    timeout: float = 3.0,
) -> dict[str, Any]:
    process = process_status()

    if not process.get(
        "pid_exists"
    ):
        _remove_pid_file()

        return {
            "ok": True,
            "stopped": False,
            "already_stopped": True,
            "execute_requested":
                bool(execute),
            "process":
                process_status(),
        }

    if not process.get(
        "owned_by_project"
    ):
        return {
            "ok": False,
            "stopped": False,
            "execute_requested":
                bool(execute),
            "reason":
                "pid_not_owned_by_project",
            "process": process,
        }

    if not execute:
        return {
            "ok": True,
            "stopped": False,
            "execute_requested":
                False,
            "reason": "dry_run",
            "process": process,
        }

    pid = int(
        process.get("pid")
        or 0
    )

    if os.name == "nt":
        subprocess.run(
            [
                "taskkill",
                "/PID",
                str(pid),
                "/T",
            ],
            check=False,
            capture_output=True,
            **_windows_hidden_process_kwargs(),
        )
    else:
        os.kill(
            pid,
            signal.SIGTERM,
        )

    deadline = (
        time.monotonic()
        + max(
            0.25,
            float(timeout),
        )
    )

    while (
        time.monotonic()
        < deadline
        and _pid_exists(pid)
    ):
        time.sleep(0.10)

    forced = False

    if _pid_exists(pid):
        if os.name == "nt":
            subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(pid),
                    "/T",
                    "/F",
                ],
                check=False,
                capture_output=True,
                **_windows_hidden_process_kwargs(),
            )
        else:
            os.kill(
                pid,
                signal.SIGKILL,
            )

        forced = True

        deadline = (
            time.monotonic()
            + 1.0
        )

        while (
            time.monotonic()
            < deadline
            and _pid_exists(pid)
        ):
            time.sleep(0.05)

    stopped = (
        not _pid_exists(pid)
    )

    if stopped:
        _remove_pid_file()

    return {
        "ok": stopped,
        "stopped": stopped,
        "forced": forced,
        "execute_requested": True,
        "process": process_status(),
    }
