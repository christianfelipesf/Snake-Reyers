from __future__ import annotations

from dataclasses import (
    asdict,
    dataclass,
    field,
)
import os
import time
from typing import (
    Any,
    Callable,
)

from cobrinha_server.core.json_store import (
    read_json,
)
from cobrinha_server.core.settings import (
    OUTPUT_METRICS_FILE,
)
from cobrinha_server.services.session_executor_plan import (
    build_identity,
)
from cobrinha_server.services.session_runtime_adapters import (
    CommandRunner,
    audio_sink_inputs_spec,
    audio_modules_spec,
    audio_prepare_spec,
    audio_remove_spec,
    audio_sinks_spec,
    matching_audio_module_ids,
    capture_start_spec,
    display_start_spec,
    game_start_spec,
)


@dataclass
class RuntimeHandle:
    role: str
    pid: int

    def public_info(
        self,
    ) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RuntimeState:
    session_id: str = ""
    state: str = "stopped"
    audio_module_id: str = ""
    display: RuntimeHandle | None = None
    game: RuntimeHandle | None = None
    window_xid: int = 0
    monitor_started: bool = False
    capture: RuntimeHandle | None = None
    destination_ready: bool = False
    completed_steps: list[str] = field(
        default_factory=list
    )
    last_error: str = ""

    def public_info(
        self,
    ) -> dict[str, Any]:
        return {
            "session_id":
                self.session_id,
            "state":
                self.state,
            "audio_module_id":
                self.audio_module_id,
            "display":
                (
                    self.display.public_info()
                    if self.display
                    else None
                ),
            "game":
                (
                    self.game.public_info()
                    if self.game
                    else None
                ),
            "window_xid":
                int(self.window_xid),
            "monitor_started":
                self.monitor_started,
            "capture":
                (
                    self.capture.public_info()
                    if self.capture
                    else None
                ),
            "destination_ready":
                self.destination_ready,
            "completed_steps":
                list(
                    self.completed_steps
                ),
            "last_error":
                self.last_error,
        }


_STATE = RuntimeState()


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float,
) -> float:
    try:
        return max(
            minimum,
            float(
                os.getenv(
                    name,
                    str(default),
                )
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        return max(
            minimum,
            default,
        )


RTMP_START_ACK_TIMEOUT_SECONDS = _env_float(
    "COBRINHA_RTMP_START_ACK_TIMEOUT",
    55.0,
    minimum=10.0,
)

GAME_BRIDGE_TIMEOUT_SECONDS = _env_float(
    "COBRINHA_GAME_BRIDGE_TIMEOUT",
    180.0,
    minimum=10.0,
)

GAME_AUDIO_ROUTE_TIMEOUT_SECONDS = _env_float(
    "COBRINHA_GAME_AUDIO_ROUTE_TIMEOUT",
    60.0,
    minimum=3.0,
)

REQUIRE_GAME_AUDIO_INPUT = (
    str(
        os.getenv(
            "COBRINHA_REQUIRE_GAME_AUDIO_INPUT",
            "0",
        )
    ).strip()
    == "1"
)


def status() -> dict[str, Any]:
    return _STATE.public_info()


def reset_state() -> dict[str, Any]:
    _STATE.session_id = ""
    _STATE.state = "stopped"
    _STATE.audio_module_id = ""
    _STATE.display = None
    _STATE.game = None
    _STATE.window_xid = 0
    _STATE.monitor_started = False
    _STATE.capture = None
    _STATE.destination_ready = False
    _STATE.completed_steps.clear()
    _STATE.last_error = ""

    return status()


def _remember_step(
    name: str,
) -> None:
    _STATE.completed_steps.append(
        str(name)
    )


def _handle_pid(
    role: str,
    handle: Any,
) -> RuntimeHandle:
    pid = int(
        getattr(
            handle,
            "pid",
            0,
        )
    )

    if pid <= 1:
        raise RuntimeError(
            f"invalid_pid:{role}"
        )

    return RuntimeHandle(
        role=role,
        pid=pid,
    )


def start_with_adapters(
    *,
    session_id: str,
    executable: str,
    server_url: str,
    display_value: str,
    username: str,
    encoder: str,
    sink: str,
    bitrate_kbps: int,
    runner: CommandRunner,
    monitor_start: Callable[
        [str],
        dict[str, Any],
    ],
    monitor_wait: Callable[
        [],
        dict[str, Any],
    ] | None = None,
    game_bridge_wait: Callable[
        [],
        dict[str, Any],
    ] | None = None,
    window_resolver: Callable[
        [int, str],
        int,
    ] | None = None,
    destination_provider: Callable[
        [],
        dict[str, Any],
    ],
) -> dict[str, Any]:
    reset_state()
    _clear_output_metrics()

    identity = build_identity(
        session_id
    )

    _STATE.session_id = (
        identity.session_id
    )
    _STATE.state = "starting"

    try:
        modules_result = runner.call(
            audio_modules_spec()
        )

        if int(
            modules_result.get(
                "returncode",
                1,
            )
        ) != 0:
            raise RuntimeError(
                "audio_modules_list_failed"
            )

        stale_audio_module_ids = (
            matching_audio_module_ids(
                modules_result.get(
                    "stdout"
                ),
                identity.audio_sink,
            )
        )

        for stale_module_id in (
            stale_audio_module_ids
        ):
            remove_result = runner.call(
                audio_remove_spec(
                    stale_module_id
                )
            )

            if int(
                remove_result.get(
                    "returncode",
                    1,
                )
            ) != 0:
                raise RuntimeError(
                    "audio_residual_remove_failed:"
                    + stale_module_id
                )

        if stale_audio_module_ids:
            _remember_step(
                "audio_residuals_cleaned"
            )

        audio_result = runner.call(
            audio_prepare_spec(
                identity
            )
        )

        if int(
            audio_result.get(
                "returncode",
                1,
            )
        ) != 0:
            raise RuntimeError(
                "audio_prepare_failed"
            )

        module_id = str(
            audio_result.get(
                "stdout"
            )
            or ""
        ).strip()

        if not module_id.isdigit():
            raise RuntimeError(
                "audio_module_id_invalid"
            )

        _STATE.audio_module_id = (
            module_id
        )

        _remember_step(
            "audio_ready"
        )

        if (
            str(display_value).strip()
            != ":0"
        ):
            display_handle = runner.spawn(
                display_start_spec(
                    display_value=
                        display_value,
                )
            )

            _STATE.display = (
                _handle_pid(
                    "display",
                    display_handle,
                )
            )

            _remember_step(
                "display_ready"
            )
        else:
            _STATE.display = None

            _remember_step(
                "native_display_ready"
            )

        game_handle = runner.spawn(
            game_start_spec(
                session_id=
                    identity.session_id,
                executable=
                    executable,
                server_url=
                    server_url,
                display_value=
                    display_value,
            )
        )

        _STATE.game = (
            _handle_pid(
                "game",
                game_handle,
            )
        )

        _remember_step(
            "game_ready"
        )

        if window_resolver is not None:
            _STATE.window_xid = int(
                window_resolver(
                    _STATE.game.pid,
                    display_value,
                )
            )

            if _STATE.window_xid <= 0:
                raise RuntimeError(
                    "game_window_not_ready"
                )

            _remember_step(
                "game_window_ready"
            )

        if game_bridge_wait is not None:
            bridge_result = (
                game_bridge_wait()
            )

            if not bool(
                bridge_result.get(
                    "ready"
                )
                or bridge_result.get(
                    "connected"
                )
            ):
                raise RuntimeError(
                    "game_bridge_not_ready:"
                    + _compact_failure_reason(
                        bridge_result
                    )
                )

            _remember_step(
                "game_bridge_ready"
            )

        audio_route_result = (
            _wait_audio_sink_input(
                runner=runner,
                sink_name=
                    identity.audio_sink,
                timeout=
                    GAME_AUDIO_ROUTE_TIMEOUT_SECONDS,
            )
        )

        if not audio_route_result.get(
            "ready"
        ):
            if REQUIRE_GAME_AUDIO_INPUT:
                raise RuntimeError(
                    "game_audio_not_ready:"
                    + _compact_failure_reason(
                        audio_route_result
                    )
                )

            _remember_step(
                "game_audio_missing"
            )
        else:
            _remember_step(
                "game_audio_ready"
            )

        monitor_result = (
            monitor_start(
                str(
                    username
                    or ""
                ).strip()
            )
        )

        monitor_ready = bool(
            monitor_result.get(
                "ready"
            )
            or monitor_result.get(
                "listening"
            )
        )

        if (
            not monitor_ready
            and monitor_wait
            is not None
        ):
            monitor_result = (
                monitor_wait()
            )

            monitor_ready = bool(
                monitor_result.get(
                    "ready"
                )
                or monitor_result.get(
                    "listening"
                )
                or monitor_result.get(
                    "connected"
                )
            )

        if not monitor_ready:
            raise RuntimeError(
                "monitor_not_ready"
            )

        _STATE.monitor_started = (
            True
        )

        _remember_step(
            "monitor_ready"
        )

        destination = (
            destination_provider()
        )

        destination_url = str(
            destination.get(
                "destination_url"
            )
            or ""
        ).strip()

        if not destination_url:
            raise RuntimeError(
                "destination_not_ready"
            )

        _STATE.destination_ready = (
            True
        )

        _remember_step(
            "destination_ready"
        )

        _clear_output_metrics()

        capture_started_at = (
            time.time()
        )
        pipeline_no_ack_timeout = max(
            35.0,
            RTMP_START_ACK_TIMEOUT_SECONDS
            + 10.0,
        )

        capture_handle = runner.spawn(
            capture_start_spec(
                display_value=
                    display_value,
                audio_monitor=
                    identity.audio_monitor,
                destination_url=
                    destination_url,
                encoder=
                    encoder,
                sink=
                    sink,
                bitrate_kbps=
                    bitrate_kbps,
                window_xid=(
                    _STATE.window_xid
                    or None
                ),
                rtmp_no_ack_timeout=
                    pipeline_no_ack_timeout,
            )
        )

        _STATE.capture = (
            _handle_pid(
                "capture",
                capture_handle,
            )
        )

        _remember_step(
            "capture_started"
        )

        initial_ack = _wait_initial_rtmp_ack(
            capture_handle,
            destination_url=
                destination_url,
            sink=
                sink,
            started_at=
                capture_started_at,
            timeout=
                RTMP_START_ACK_TIMEOUT_SECONDS,
        )

        if not initial_ack.get(
            "ok"
        ):
            if _initial_ack_can_keep_running(
                initial_ack
            ):
                _STATE.state = "running"
                _STATE.last_error = (
                    "rtmp_ack_pending:"
                    + str(
                        initial_ack.get(
                            "error"
                        )
                        or initial_ack.get(
                            "reason"
                        )
                        or "rtmp_ack_missing"
                    )
                )

                _remember_step(
                    "capture_waiting_for_rtmp_ack"
                )

                return {
                    "ok": True,
                    "state":
                        _STATE.state,
                    "warning":
                        "rtmp_ack_pending",
                    "initial_ack":
                        initial_ack,
                    "runtime":
                        status(),
                }

            raise RuntimeError(
                "capture_not_ready:"
                + str(
                    initial_ack.get(
                        "error"
                    )
                    or initial_ack.get(
                        "reason"
                    )
                    or "rtmp_ack_missing"
                )
            )

        _remember_step(
            "capture_ready"
        )

        _STATE.state = "running"

        return {
            "ok": True,
            "state":
                _STATE.state,
            "runtime":
                status(),
        }

    except Exception as exc:
        _STATE.state = "error"
        _STATE.last_error = (
            f"{type(exc).__name__}:{exc}"
        )
        raise


def _clear_output_metrics() -> None:
    try:
        OUTPUT_METRICS_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _wait_audio_sink_input(
    *,
    runner: CommandRunner,
    sink_name: str,
    timeout: float,
    interval: float = 0.25,
) -> dict[str, Any]:
    sink_name = str(
        sink_name
        or ""
    ).strip()

    if not sink_name:
        return {
            "ready": False,
            "reason": "sink_name_empty",
        }

    deadline = (
        time.monotonic()
        + max(
            1.0,
            float(timeout or 0.0),
        )
    )

    last: dict[str, Any] = {
        "reason": "not_checked",
        "sink_name": sink_name,
    }

    while (
        time.monotonic()
        < deadline
    ):
        sinks_result = runner.call(
            audio_sinks_spec()
        )

        if int(
            sinks_result.get(
                "returncode",
                1,
            )
        ) != 0:
            last = {
                "reason": "sinks_list_failed",
                "stderr": str(
                    sinks_result.get(
                        "stderr"
                    )
                    or ""
                ).strip()[:160],
            }
            time.sleep(
                max(0.05, float(interval))
            )
            continue

        sink_id = _find_sink_id(
            sinks_result.get(
                "stdout"
            ),
            sink_name,
        )

        if not sink_id:
            last = {
                "reason": "sink_not_found",
                "sink_name": sink_name,
            }
            time.sleep(
                max(0.05, float(interval))
            )
            continue

        inputs_result = runner.call(
            audio_sink_inputs_spec()
        )

        if int(
            inputs_result.get(
                "returncode",
                1,
            )
        ) != 0:
            last = {
                "reason":
                    "sink_inputs_list_failed",
                "sink_name": sink_name,
                "sink_id": sink_id,
                "stderr": str(
                    inputs_result.get(
                        "stderr"
                    )
                    or ""
                ).strip()[:160],
            }
            time.sleep(
                max(0.05, float(interval))
            )
            continue

        input_count = _count_sink_inputs(
            inputs_result.get(
                "stdout"
            ),
            sink_id,
        )

        if input_count > 0:
            return {
                "ready": True,
                "reason": "sink_input_ready",
                "sink_name": sink_name,
                "sink_id": sink_id,
                "input_count": input_count,
            }

        last = {
            "reason": "no_sink_input",
            "sink_name": sink_name,
            "sink_id": sink_id,
        }

        time.sleep(
            max(0.05, float(interval))
        )

    return {
        "ready": False,
        **last,
    }


def _find_sink_id(
    output: object,
    sink_name: str,
) -> str:
    expected = str(
        sink_name
        or ""
    ).strip()

    if not expected:
        return ""

    for raw_line in str(
        output
        or ""
    ).splitlines():
        parts = raw_line.split(
            "\t"
        )

        if len(parts) < 2:
            continue

        sink_id = parts[0].strip()
        name = parts[1].strip()

        if (
            name == expected
            and sink_id
        ):
            return sink_id

    return ""


def _count_sink_inputs(
    output: object,
    sink_id: str,
) -> int:
    expected = str(
        sink_id
        or ""
    ).strip()

    if not expected:
        return 0

    count = 0
    current: list[str] = []

    def flush() -> None:
        nonlocal count

        if not current:
            return

        for raw_line in current:
            clean = raw_line.strip()

            if not clean.startswith(
                "Sink:"
            ):
                continue

            value = (
                clean.split(
                    ":",
                    1,
                )[1].strip()
            )

            if value == expected:
                count += 1

            return

    for raw_line in str(
        output
        or ""
    ).splitlines():
        if raw_line.startswith(
            "Sink Input #"
        ):
            flush()
            current = [
                raw_line,
            ]
        else:
            current.append(
                raw_line
            )

    flush()

    return count


def _compact_failure_reason(
    payload: dict[str, Any],
) -> str:
    if not isinstance(
        payload,
        dict,
    ):
        return "unknown"

    for key in (
        "reason",
        "error",
        "state",
    ):
        value = payload.get(
            key
        )

        if value:
            return str(
                value
            )[:220]

    return "unknown"


def _wait_initial_rtmp_ack(
    handle: Any,
    *,
    destination_url: str,
    sink: str,
    started_at: float,
    timeout: float,
) -> dict[str, Any]:
    if not str(
        destination_url
        or ""
    ).strip():
        return {
            "ok": True,
            "reason": "destination_empty",
        }

    if str(
        sink
        or ""
    ).strip().lower() != "rtmp2sink":
        return {
            "ok": True,
            "reason": "sink_sem_ack_stats",
        }

    pid = int(
        getattr(
            handle,
            "pid",
            0,
        )
        or 0
    )

    deadline = (
        time.time()
        + max(
            1.0,
            float(
                timeout
                or 0.0
            ),
        )
    )

    saw_stats = False
    max_out_total = 0
    max_unacked = 0
    max_no_ack_seconds = 0.0
    max_ack_window = 2_500_000
    last_rtmp: dict[str, Any] = {}
    last_audio: dict[str, Any] = {}

    while (
        time.time()
        < deadline
    ):
        try:
            returncode = handle.poll()
        except Exception:
            returncode = None

        if returncode is not None:
            return {
                "ok": False,
                "reason": "capture_exited",
                "error":
                    "captura encerrou antes do ACK "
                    f"rc={returncode}"
                    + _audio_error_suffix(
                        last_audio
                    ),
                "last_rtmp": last_rtmp,
                "last_audio": last_audio,
            }

        metrics = read_json(
            OUTPUT_METRICS_FILE,
            {},
        )

        if isinstance(
            metrics,
            dict,
        ):
            metric_pid = _safe_int(
                metrics.get(
                    "pid"
                )
            )
            updated_at = _safe_float(
                metrics.get(
                    "updated_at"
                )
            )

            if (
                (
                    not metric_pid
                    or not pid
                    or metric_pid == pid
                )
                and updated_at >= started_at - 0.5
            ):
                rtmp = metrics.get(
                    "rtmp"
                )
                audio = metrics.get(
                    "audio"
                )

                if isinstance(
                    audio,
                    dict,
                ):
                    last_audio = dict(
                        audio
                    )

                if isinstance(
                    rtmp,
                    dict,
                ) and rtmp.get(
                    "has_stats"
                ):
                    saw_stats = True
                    last_rtmp = dict(
                        rtmp
                    )
                    out_total = _safe_int(
                        rtmp.get(
                            "out_total"
                        )
                    )
                    out_acked = _safe_int(
                        rtmp.get(
                            "out_acked"
                        )
                    )
                    unacked = _safe_int(
                        rtmp.get(
                            "unacked"
                        )
                    )
                    no_ack_seconds = _safe_float(
                        rtmp.get(
                            "no_ack_seconds"
                        )
                    )
                    ack_window = max(
                        _safe_int(
                            rtmp.get(
                                "out_window_ack"
                            )
                        ),
                        _safe_int(
                            rtmp.get(
                                "in_window_ack"
                            )
                        ),
                        2_500_000,
                    )

                    max_ack_window = max(
                        max_ack_window,
                        ack_window,
                    )
                    max_no_ack_seconds = max(
                        max_no_ack_seconds,
                        no_ack_seconds,
                    )

                    if out_total >= max_out_total:
                        max_out_total = out_total
                        max_unacked = unacked

                    if out_acked > 0:
                        return {
                            "ok": True,
                            "reason": "ack_ok",
                            "rtmp": last_rtmp,
                        }

        time.sleep(
            0.5
        )

    if saw_stats:
        if max_out_total < max_ack_window:
            reason = "low_initial_output"
            error = (
                "saida inicial muito baixa "
                f"out_total={max_out_total} "
                f"minimo_ack={max_ack_window}"
                + _audio_error_suffix(
                    last_audio
                )
            )
        else:
            reason = "no_initial_ack"
            error = (
                "sem ACK inicial "
                f"no_ack_seconds={int(max_no_ack_seconds or timeout)} "
                f"max_out_total={max_out_total} "
                f"max_unacked={max_unacked}"
                + _audio_error_suffix(
                    last_audio
                )
            )
    else:
        reason = "no_rtmp_metrics"
        error = (
            "sem metricas RTMP "
            f"por {int(timeout)}s"
            + _audio_error_suffix(
                last_audio
            )
        )

    return {
        "ok": False,
        "reason": reason,
        "error": error,
        "last_rtmp": last_rtmp,
        "last_audio": last_audio,
        "max_out_total": max_out_total,
        "max_unacked": max_unacked,
    }


def _initial_ack_can_keep_running(
    payload: dict[str, Any],
) -> bool:
    if not isinstance(
        payload,
        dict,
    ):
        return False

    reason = str(
        payload.get(
            "reason"
        )
        or ""
    ).casefold()

    error = str(
        payload.get(
            "error"
        )
        or ""
    ).casefold()

    text = (
        reason
        + " "
        + error
    )

    return any(
        marker in text
        for marker in (
            "no_initial_ack",
            "rtmp_ack_missing",
            "sem ack inicial",
        )
    )


def _audio_error_suffix(
    audio: dict[str, Any],
) -> str:
    if not isinstance(
        audio,
        dict,
    ):
        return ""

    rms_values = audio.get(
        "rms"
    )

    if not isinstance(
        rms_values,
        list,
    ):
        return ""

    numeric = [
        _safe_float(value)
        for value in rms_values
        if isinstance(
            value,
            (
                int,
                float,
                str,
            ),
        )
    ]

    if (
        numeric
        and max(numeric) <= -120.0
    ):
        return (
            "; audio capturado em silencio absoluto"
        )

    return ""


def _safe_int(
    value: object,
) -> int:
    try:
        return int(
            float(
                value
                or 0
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0


def _safe_float(
    value: object,
) -> float:
    try:
        return float(
            value
            or 0.0
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def rollback_with_adapters(
    *,
    runner: CommandRunner,
    monitor_stop: Callable[
        [],
        dict[str, Any],
    ],
    process_stop: Callable[
        [str, int],
        bool,
    ],
) -> dict[str, Any]:
    actions: list[
        dict[str, Any]
    ] = []

    ok = True

    def stop_process(
        role: str,
        handle: RuntimeHandle | None,
    ) -> None:
        nonlocal ok

        if handle is None:
            return

        stopped = bool(
            process_stop(
                role,
                handle.pid,
            )
        )

        actions.append(
            {
                "role": role,
                "stopped": stopped,
                "pid": handle.pid,
            }
        )

        if not stopped:
            ok = False

    stop_process(
        "capture",
        _STATE.capture,
    )

    _STATE.capture = None

    if _STATE.monitor_started:
        monitor_result = (
            monitor_stop()
        )

        monitor_ok = bool(
            monitor_result.get(
                "ok",
                False,
            )
        )

        actions.append(
            {
                "role":
                    "monitor",
                "stopped":
                    monitor_ok,
            }
        )

        if not monitor_ok:
            ok = False

        _STATE.monitor_started = (
            False
        )

    stop_process(
        "game",
        _STATE.game,
    )

    _STATE.game = None
    _STATE.window_xid = 0

    stop_process(
        "display",
        _STATE.display,
    )

    _STATE.display = None

    if _STATE.audio_module_id:
        result = runner.call(
            audio_remove_spec(
                _STATE.audio_module_id
            )
        )

        audio_ok = (
            int(
                result.get(
                    "returncode",
                    1,
                )
            )
            == 0
        )

        actions.append(
            {
                "role":
                    "audio",
                "stopped":
                    audio_ok,
                "module_id":
                    _STATE.audio_module_id,
            }
        )

        if not audio_ok:
            ok = False

        _STATE.audio_module_id = ""

    _STATE.destination_ready = False

    if ok:
        _STATE.state = "stopped"
        _STATE.session_id = ""
        _STATE.last_error = ""
        _STATE.completed_steps.clear()
    else:
        _STATE.state = (
            "rollback_partial"
        )

    return {
        "ok": ok,
        "state":
            _STATE.state,
        "actions":
            actions,
    }


def start_with_rollback(
    *,
    session_id: str,
    executable: str,
    server_url: str,
    display_value: str,
    username: str,
    encoder: str,
    sink: str,
    bitrate_kbps: int,
    runner: CommandRunner,
    monitor_start: Callable[
        [str],
        dict[str, Any],
    ],
    monitor_wait: Callable[
        [],
        dict[str, Any],
    ] | None = None,
    game_bridge_wait: Callable[
        [],
        dict[str, Any],
    ] | None = None,
    window_resolver: Callable[
        [int, str],
        int,
    ] | None = None,
    monitor_stop: Callable[
        [],
        dict[str, Any],
    ],
    destination_provider: Callable[
        [],
        dict[str, Any],
    ],
    process_stop: Callable[
        [str, int],
        bool,
    ],
) -> dict[str, Any]:
    try:
        return start_with_adapters(
            session_id=
                session_id,
            executable=
                executable,
            server_url=
                server_url,
            display_value=
                display_value,
            username=
                username,
            encoder=
                encoder,
            sink=
                sink,
            bitrate_kbps=
                bitrate_kbps,
            runner=
                runner,
            monitor_start=
                monitor_start,
            monitor_wait=
                monitor_wait,
            game_bridge_wait=
                game_bridge_wait,
            window_resolver=
                window_resolver,
            destination_provider=
                destination_provider,
        )

    except Exception as exc:
        error_text = (
            f"{type(exc).__name__}:{exc}"
        )
        completed_steps = list(
            _STATE.completed_steps
        )
        destination_was_ready = bool(
            _STATE.destination_ready
        )
        capture_was_started = (
            _STATE.capture is not None
        )
        rollback = (
            rollback_with_adapters(
                runner=
                    runner,
                monitor_stop=
                    monitor_stop,
                process_stop=
                    process_stop,
            )
        )
        _STATE.state = "failed"
        _STATE.last_error = error_text
        _STATE.completed_steps = [
            *completed_steps,
            "rollback_complete",
        ]

        return {
            "ok": False,
            "state": "failed",
            "error":
                error_text,
            "external_destination_started":
                destination_was_ready,
            "capture_started":
                capture_was_started,
            "completed_steps_before_failure":
                completed_steps,
            "rollback":
                rollback,
            "runtime":
                status(),
        }
