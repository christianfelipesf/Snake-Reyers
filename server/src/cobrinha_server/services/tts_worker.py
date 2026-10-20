from __future__ import annotations

import threading
import time
from typing import Any

from cobrinha_server.core.json_store import (
    read_json,
    write_json_atomic,
)
from cobrinha_server.core.settings import RUNS_DIR
from cobrinha_server.services.speech_queue import (
    pop_pending,
    prepare_pending_job,
    push_ready,
)


WORKER_STATUS_FILE = (
    RUNS_DIR / "tts_worker_status.json"
)

_WORKER_THREAD: threading.Thread | None = None
_STOP = threading.Event()


def start_tts_worker() -> None:
    global _WORKER_THREAD

    if (
        _WORKER_THREAD is not None
        and _WORKER_THREAD.is_alive()
    ):
        return

    _STOP.clear()

    _WORKER_THREAD = threading.Thread(
        target=_worker_loop,
        name="cobrinha-tts-worker",
        daemon=True,
    )

    _WORKER_THREAD.start()


def stop_tts_worker() -> None:
    _STOP.set()


def worker_status() -> dict[str, Any]:
    raw = read_json(
        WORKER_STATUS_FILE,
        {},
    )

    return (
        dict(raw)
        if isinstance(raw, dict)
        else {}
    )


def reset_transient_state(
    *,
    reason: str = "live_session_reset",
) -> dict[str, Any]:
    payload = {
        "state": "idle",
        "reason": str(reason or "live_session_reset"),
        "updated_at": time.time(),
    }
    _write_status(payload)
    return dict(payload)


def _worker_loop() -> None:
    while not _STOP.is_set():
        job = pop_pending()

        if not job:
            _write_status(
                {
                    "state": "idle",
                    "updated_at":
                        time.time(),
                }
            )

            _STOP.wait(0.18)
            continue

        _write_status(
            {
                "state": "preparing",
                "job_id":
                    job.get("id"),
                "updated_at":
                    time.time(),
            }
        )

        try:
            ready = prepare_pending_job(
                job
            )

        except Exception as exc:
            ready = {
                **job,
                "prepare_error":
                    f"{type(exc).__name__}: {exc}",
                "prepared_at":
                    time.time(),
            }

            _write_status(
                {
                    "state": "error",
                    "job_id":
                        job.get("id"),
                    "error":
                        ready["prepare_error"],
                    "updated_at":
                        time.time(),
                }
            )

        else:
            _write_status(
                {
                    "state": "prepared",
                    "job_id":
                        job.get("id"),
                    "updated_at":
                        time.time(),
                }
            )

        push_ready(ready)


def _write_status(
    payload: dict[str, Any],
) -> None:
    try:
        write_json_atomic(
            WORKER_STATUS_FILE,
            payload,
        )
    except OSError:
        # Status is diagnostic only and must never stop speech generation.
        pass
