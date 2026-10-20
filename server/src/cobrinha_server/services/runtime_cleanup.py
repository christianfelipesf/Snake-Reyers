from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from cobrinha_server.core.json_store import (
    read_json,
    write_json_atomic,
)
from cobrinha_server.core.settings import LOGS_DIR, RUNS_DIR


PREPARED_AUDIO_DIR = RUNS_DIR / "prepared_audio"
PROFILE_AVATAR_DIR = RUNS_DIR / "profile_avatars"
SPEECH_TEST_DIR = RUNS_DIR / "speech_test"
STATE_FILE = RUNS_DIR / "runtime_cleanup.json"
AUTO_CLEANUP_INTERVAL_LIVES = 3
REFERENCE_STATE_FILES = (
    RUNS_DIR / "speech_active.json",
    RUNS_DIR / "speech_pending_queue.json",
    RUNS_DIR / "speech_ready_queue.json",
    RUNS_DIR / "speech_ready_pair_queue.json",
    RUNS_DIR / "speech_pair_playback.json",
    RUNS_DIR / "speech_manual_sequence.json",
    RUNS_DIR / "social_live_events.json",
    RUNS_DIR / "top_supporters_live.json",
)

_LOCK = threading.Lock()


def _default_state() -> dict[str, Any]:
    return {
        "completed_lives": 0,
        "cleanup_every_lives": AUTO_CLEANUP_INTERVAL_LIVES,
        "last_live_completed_at": 0.0,
        "last_cleanup_at": 0.0,
        "last_cleanup_trigger": "",
        "last_cleanup_ok": None,
    }


def _read_state() -> dict[str, Any]:
    raw = read_json(STATE_FILE, {})
    if not isinstance(raw, dict):
        raw = {}

    state = {
        **_default_state(),
        **raw,
    }
    try:
        completed_lives = int(state.get("completed_lives") or 0)
    except (TypeError, ValueError):
        completed_lives = 0
    state["completed_lives"] = max(0, completed_lives)
    state["cleanup_every_lives"] = AUTO_CLEANUP_INTERVAL_LIVES
    return state


def automatic_cleanup_status() -> dict[str, Any]:
    with _LOCK:
        state = _read_state()
    completed_lives = int(state["completed_lives"])
    return {
        **state,
        "remaining_lives": max(
            0,
            AUTO_CLEANUP_INTERVAL_LIVES - completed_lives,
        ),
        "cleanup_due": completed_lives >= AUTO_CLEANUP_INTERVAL_LIVES,
    }


def _resolved(path: Path) -> str:
    return str(path.expanduser().resolve())


def _collect_path_strings(value: Any, output: set[str]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _collect_path_strings(item, output)
        return
    if isinstance(value, list):
        for item in value:
            _collect_path_strings(item, output)
        return
    if not isinstance(value, str):
        return

    clean = value.strip()
    if not clean:
        return

    candidate = Path(clean).expanduser()
    if not candidate.is_absolute():
        return

    candidate = candidate.resolve()

    if (
        PREPARED_AUDIO_DIR.resolve() in candidate.parents
        or PROFILE_AVATAR_DIR.resolve() in candidate.parents
    ):
        output.add(_resolved(candidate))


def protected_runtime_files() -> set[str]:
    protected: set[str] = set()
    for path in REFERENCE_STATE_FILES:
        _collect_path_strings(read_json(path, None), protected)
    return protected


def _file_item(path: Path, category: str) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "kind": "file",
        "category": category,
        "path": str(path),
        "bytes": int(size),
    }


def _stale_pid_file(path: Path) -> bool:
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return True

    if pid <= 0:
        return True

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _candidate_items() -> list[dict[str, Any]]:
    protected = protected_runtime_files()
    items: list[dict[str, Any]] = []

    for directory, category in (
        (PREPARED_AUDIO_DIR, "falas_preparadas"),
        (PROFILE_AVATAR_DIR, "cache_avatares"),
        (SPEECH_TEST_DIR, "testes_de_voz"),
    ):
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or _resolved(path) in protected:
                continue
            items.append(_file_item(path, category))

    if RUNS_DIR.is_dir():
        for path in RUNS_DIR.iterdir():
            if not path.is_file():
                continue
            if path.name.startswith("tmp") or ".bak_" in path.name:
                items.append(_file_item(path, "temporarios_incompletos"))
            elif path == STATE_FILE:
                items.append(_file_item(path, "historico_da_limpeza"))
            elif path.suffix == ".pid" and _stale_pid_file(path):
                items.append(_file_item(path, "pids_inativos"))

    if LOGS_DIR.is_dir():
        for path in LOGS_DIR.iterdir():
            if path.is_file():
                items.append(_file_item(path, "logs_de_live"))

    return items


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, dict[str, int]] = {}
    total_bytes = 0
    for item in items:
        category = str(item.get("category") or "outros")
        size = int(item.get("bytes") or 0)
        total_bytes += size
        state = categories.setdefault(category, {"items": 0, "bytes": 0})
        state["items"] += 1
        state["bytes"] += size
    return {
        "items": len(items),
        "bytes": total_bytes,
        "categories": categories,
    }


def analyze() -> dict[str, Any]:
    with _LOCK:
        items = _candidate_items()
        state = _read_state()
        return {
            "ok": True,
            "mode": "analysis",
            "policy": "remove_all_transient_history",
            "protected_files": len(protected_runtime_files()),
            "automatic_cleanup": {
                **state,
                "remaining_lives": max(
                    0,
                    AUTO_CLEANUP_INTERVAL_LIVES
                    - int(state["completed_lives"]),
                ),
            },
            **_summary(items),
        }


def cleanup(*, trigger: str = "manual") -> dict[str, Any]:
    started_at = time.time()
    with _LOCK:
        previous_state = _read_state()
        items = _candidate_items()
        removed: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        for item in items:
            path = Path(str(item.get("path") or ""))
            try:
                if item.get("kind") == "directory":
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
                removed.append(item)
            except OSError as exc:
                errors.append(
                    {
                        "path": str(path),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        for directory in (
            PREPARED_AUDIO_DIR,
            PROFILE_AVATAR_DIR,
            SPEECH_TEST_DIR,
        ):
            try:
                subdirectories = sorted(
                    (path for path in directory.rglob("*") if path.is_dir()),
                    key=lambda path: len(path.parts),
                    reverse=True,
                )
                for subdirectory in subdirectories:
                    if not any(subdirectory.iterdir()):
                        subdirectory.rmdir()
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()
                    directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                errors.append(
                    {
                        "path": str(directory),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        result = {
            "ok": not errors,
            "mode": "cleanup",
            "policy": "remove_all_transient_history",
            "started_at": started_at,
            "finished_at": time.time(),
            "protected_files": len(protected_runtime_files()),
            **_summary(removed),
            "errors": errors[:20],
            "error_count": len(errors),
        }

        state = {
            **previous_state,
            "completed_lives": (
                0
                if result["ok"]
                else int(previous_state["completed_lives"])
            ),
            "cleanup_every_lives": AUTO_CLEANUP_INTERVAL_LIVES,
            "last_cleanup_at": time.time(),
            "last_cleanup_trigger": str(trigger or "manual"),
            "last_cleanup_ok": bool(result["ok"]),
        }
        write_json_atomic(STATE_FILE, state)
        result["automatic_cleanup"] = {
            **state,
            "remaining_lives": max(
                0,
                AUTO_CLEANUP_INTERVAL_LIVES
                - int(state["completed_lives"]),
            ),
        }
        return result


def register_completed_live() -> dict[str, Any]:
    completed_at = time.time()
    with _LOCK:
        state = _read_state()
        state["completed_lives"] = int(state["completed_lives"]) + 1
        state["last_live_completed_at"] = completed_at
        write_json_atomic(STATE_FILE, state)

    completed_lives = int(state["completed_lives"])
    if completed_lives < AUTO_CLEANUP_INTERVAL_LIVES:
        return {
            "ok": True,
            "counted": True,
            "cleanup_triggered": False,
            "deferred": False,
            **automatic_cleanup_status(),
        }

    result = cleanup(trigger="three_completed_lives")
    return {
        "ok": bool(result.get("ok")),
        "counted": True,
        "cleanup_triggered": True,
        "deferred": False,
        "cleanup": result,
        **automatic_cleanup_status(),
    }
