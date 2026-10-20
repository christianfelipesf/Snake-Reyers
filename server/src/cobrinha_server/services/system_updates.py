from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from types import ModuleType
from typing import Any

from cobrinha_server.core.settings import (
    PROJECT_DIR,
    application_version,
)


ROOT_DIR = PROJECT_DIR.parent
UPDATER_PATH = ROOT_DIR / "launcher" / "update.py"
RESTARTER_PATH = ROOT_DIR / "launcher" / "restart.py"


class SystemUpdateBusy(RuntimeError):
    pass


_lock = threading.Lock()
_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "busy": False,
    "checked_at": "",
    "available": "",
    "update_available": False,
    "installed": False,
    "restart_scheduled": False,
    "message": "Atualização do sistema ainda não consultada.",
    "last_error": "",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_updater() -> ModuleType:
    if not UPDATER_PATH.is_file():
        raise FileNotFoundError(
            f"Atualizador não encontrado: {UPDATER_PATH}"
        )
    spec = importlib.util.spec_from_file_location(
        "snake_reyers_panel_updater",
        UPDATER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Não foi possível carregar o atualizador.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public_status() -> dict[str, Any]:
    with _state_lock:
        snapshot = dict(_state)
    return {
        "ok": not bool(snapshot.get("last_error")),
        "current": application_version(),
        **snapshot,
    }


def synchronize(*, install: bool) -> dict[str, Any]:
    if not _lock.acquire(blocking=False):
        raise SystemUpdateBusy(
            "Já existe uma atualização do sistema em andamento."
        )

    with _state_lock:
        _state.update(
            {
                "busy": True,
                "installed": False,
                "restart_scheduled": False,
                "message": (
                    "Baixando e instalando a atualização..."
                    if install
                    else "Verificando atualização..."
                ),
                "last_error": "",
            }
        )

    try:
        updater = _load_updater()
        manifest_url = updater._manifest_url()
        if not manifest_url:
            raise RuntimeError("Manifesto de atualização não configurado.")
        result = updater.check_and_update(manifest_url, install)
        installed = bool(result.get("installed"))
        available = str(result.get("available") or "")
        update_available = bool(result.get("update_available"))

        if installed:
            message = (
                f"Versão {available} instalada. O sistema será reiniciado."
            )
        elif update_available:
            message = f"Versão {available} disponível para instalação."
        else:
            message = "O Snake Reyers já está atualizado."

        with _state_lock:
            _state.update(
                {
                    "checked_at": _utc_now(),
                    "available": available,
                    "update_available": update_available,
                    "installed": installed,
                    "message": message,
                    "last_error": "",
                }
            )
    except Exception as exc:
        with _state_lock:
            _state.update(
                {
                    "checked_at": _utc_now(),
                    "message": "Não foi possível atualizar o sistema.",
                    "last_error": str(exc),
                }
            )
        raise
    finally:
        with _state_lock:
            _state["busy"] = False
        _lock.release()

    return public_status()


def schedule_restart(delay_seconds: float = 2.0) -> None:
    if not RESTARTER_PATH.is_file():
        raise FileNotFoundError(
            f"Reiniciador não encontrado: {RESTARTER_PATH}"
        )

    command = [
        sys.executable,
        str(RESTARTER_PATH),
        "--wait-pid",
        str(os.getpid()),
        "--root",
        str(ROOT_DIR),
    ]
    kwargs: dict[str, Any] = {
        "cwd": str(ROOT_DIR),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen(command, **kwargs)
    with _state_lock:
        _state["restart_scheduled"] = True
        _state["message"] = "Atualização instalada. Reiniciando o sistema..."

    timer = threading.Timer(delay_seconds, os._exit, args=(0,))
    timer.daemon = True
    timer.start()
