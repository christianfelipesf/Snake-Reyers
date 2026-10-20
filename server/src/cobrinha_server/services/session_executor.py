from __future__ import annotations

from dataclasses import (
    asdict,
    dataclass,
)
from typing import (
    Any,
    Callable,
    Protocol,
)

from cobrinha_server.services.session_executor_plan import (
    GameLaunchPlan,
    OwnershipRecord,
    build_game_plan,
    build_identity,
    game_ownership_record,
    ownership_matches,
    planned_sequence,
)


class ProcessLike(
    Protocol
):
    pid: int

    def poll(
        self,
    ) -> int | None:
        ...


ProcessFactory = Callable[
    [GameLaunchPlan],
    ProcessLike,
]

ProcessInspector = Callable[
    [int],
    dict[str, Any],
]

ProcessTerminator = Callable[
    [int],
    bool,
]


@dataclass
class ManagedProcess:
    role: str
    pid: int
    ownership: OwnershipRecord
    running: bool = True

    def public_info(
        self,
    ) -> dict[str, Any]:
        return {
            "role": self.role,
            "pid": self.pid,
            "running": self.running,
            "ownership":
                self.ownership.public_info(),
        }


@dataclass
class ExecutorState:
    session_id: str = ""
    state: str = "stopped"
    game: ManagedProcess | None = None
    last_error: str = ""

    def public_info(
        self,
    ) -> dict[str, Any]:
        return {
            "session_id":
                self.session_id,
            "state":
                self.state,
            "game":
                (
                    self.game.public_info()
                    if self.game
                    else None
                ),
            "last_error":
                self.last_error,
        }


_STATE = ExecutorState()


def status() -> dict[str, Any]:
    return _STATE.public_info()


def reset_state() -> dict[str, Any]:
    _STATE.session_id = ""
    _STATE.state = "stopped"
    _STATE.game = None
    _STATE.last_error = ""

    return status()


def build_execution_preview(
    *,
    session_id: str,
    executable: str,
    server_url: str,
    display_value: str,
) -> dict[str, Any]:
    identity = build_identity(
        session_id
    )

    plan = build_game_plan(
        session_id=
            identity.session_id,
        executable=
            executable,
        server_url=
            server_url,
        display_value=
            display_value,
    )

    return {
        "identity":
            identity.public_info(),
        "game_plan":
            plan.public_info(),
        "sequence":
            list(
                planned_sequence()
            ),
        "execution": False,
    }


def launch_game_with_factory(
    *,
    session_id: str,
    executable: str,
    server_url: str,
    display_value: str,
    process_factory: ProcessFactory,
) -> dict[str, Any]:
    if process_factory is None:
        raise RuntimeError(
            "process_factory_required"
        )

    if (
        _STATE.game is not None
        and _STATE.game.running
    ):
        raise RuntimeError(
            "game_already_managed"
        )

    plan = build_game_plan(
        session_id=session_id,
        executable=executable,
        server_url=server_url,
        display_value=display_value,
    )

    _STATE.session_id = (
        build_identity(
            session_id
        ).session_id
    )
    _STATE.state = "starting_game"
    _STATE.last_error = ""

    try:
        process = process_factory(
            plan
        )

        pid = int(
            process.pid
        )

        if pid <= 1:
            raise RuntimeError(
                "invalid_pid"
            )

        record = game_ownership_record(
            pid=pid,
            session_id=
                _STATE.session_id,
        )

        managed = ManagedProcess(
            role="game",
            pid=pid,
            ownership=record,
            running=True,
        )

        _STATE.game = managed
        _STATE.state = "game_started"

        return {
            "ok": True,
            "state":
                _STATE.state,
            "process":
                managed.public_info(),
            "plan":
                plan.public_info(),
        }

    except Exception as exc:
        _STATE.state = "error"
        _STATE.last_error = (
            f"{type(exc).__name__}:{exc}"
        )
        _STATE.game = None
        raise


def verify_managed_game(
    *,
    inspector: ProcessInspector,
) -> dict[str, Any]:
    managed = _STATE.game

    if managed is None:
        return {
            "ok": False,
            "reason":
                "no_managed_game",
        }

    details = inspector(
        managed.pid
    )

    actual_cwd = str(
        details.get("cwd")
        or ""
    )

    actual_command = str(
        details.get("command")
        or ""
    )

    matched = ownership_matches(
        managed.ownership,
        actual_cwd=actual_cwd,
        actual_command=
            actual_command,
    )

    return {
        "ok": matched,
        "pid": managed.pid,
        "ownership_match":
            matched,
    }


def stop_managed_game_with_factory(
    *,
    inspector: ProcessInspector,
    terminator: ProcessTerminator,
) -> dict[str, Any]:
    managed = _STATE.game

    if managed is None:
        return {
            "ok": True,
            "stopped": False,
            "reason":
                "no_managed_game",
        }

    verification = (
        verify_managed_game(
            inspector=inspector
        )
    )

    if not verification.get(
        "ownership_match"
    ):
        _STATE.state = (
            "ownership_mismatch"
        )
        _STATE.last_error = (
            "managed_pid_not_owned"
        )

        return {
            "ok": False,
            "stopped": False,
            "reason":
                "ownership_mismatch",
            "pid":
                managed.pid,
        }

    stopped = bool(
        terminator(
            managed.pid
        )
    )

    if not stopped:
        _STATE.state = (
            "stop_failed"
        )
        _STATE.last_error = (
            "terminator_failed"
        )

        return {
            "ok": False,
            "stopped": False,
            "reason":
                "terminator_failed",
            "pid":
                managed.pid,
        }

    managed.running = False
    _STATE.game = None
    _STATE.state = "stopped"
    _STATE.session_id = ""
    _STATE.last_error = ""

    return {
        "ok": True,
        "stopped": True,
    }


def rollback_with_factories(
    *,
    inspector: ProcessInspector,
    terminator: ProcessTerminator,
) -> dict[str, Any]:
    result = (
        stop_managed_game_with_factory(
            inspector=inspector,
            terminator=terminator,
        )
    )

    if result.get("ok"):
        _STATE.state = "stopped"
    else:
        _STATE.state = (
            "rollback_blocked"
        )

    return {
        "ok":
            bool(result.get("ok")),
        "game":
            result,
        "state":
            _STATE.state,
    }
