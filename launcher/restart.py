#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import socket
import subprocess
import time
from pathlib import Path


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _wait_for_shutdown(pid: int, port: int, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _process_exists(pid) and not _port_open(port):
            return
        time.sleep(0.25)
    raise TimeoutError("O servidor anterior não encerrou a tempo.")


def _start(root: Path) -> None:
    system = platform.system().lower()
    environment = os.environ.copy()
    environment["SNAKE_REYERS_SKIP_BROWSER"] = "1"
    if system == "windows":
        script = root / "launcher" / "start_windows.ps1"
        flags = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
            env=environment,
        )
        return

    if system == "linux":
        script = root / "launcher" / "start_linux.sh"
        subprocess.Popen(
            ["bash", str(script)],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            env=environment,
        )
        return

    raise RuntimeError(f"Plataforma não suportada: {system}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reiniciador do Snake Reyers")
    parser.add_argument("--wait-pid", type=int, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=9393)
    arguments = parser.parse_args()

    _wait_for_shutdown(arguments.wait_pid, arguments.port)
    _start(arguments.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
