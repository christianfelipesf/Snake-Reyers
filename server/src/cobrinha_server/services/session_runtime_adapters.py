from __future__ import annotations

from dataclasses import (
    asdict,
    dataclass,
)
import os
from pathlib import Path
import sys
from typing import (
    Any,
    Callable,
    Protocol,
)

from cobrinha_server.core.settings import (
    LOGS_DIR,
    OUTPUT_AUDIO_BITRATE,
    OUTPUT_AUDIO_RATE,
    OUTPUT_FPS,
    OUTPUT_HEIGHT,
    OUTPUT_LOG_FILE,
    OUTPUT_METRICS_FILE,
    OUTPUT_WIDTH,
    PROJECT_DIR,
)
from cobrinha_server.services.session_executor_plan import (
    GAME_DIR,
    GameLaunchPlan,
    SessionIdentity,
    build_game_plan,
    build_identity,
)


REAL_EXECUTION_ENV = (
    "COBRINHA_ALLOW_REAL_SESSION_EXECUTION"
)


class RuntimeExecutionBlocked(
    RuntimeError
):
    pass


class CommandHandle(
    Protocol
):
    pid: int

    def poll(
        self,
    ) -> int | None:
        ...


class CommandRunner(
    Protocol
):
    def spawn(
        self,
        spec: "CommandSpec",
    ) -> CommandHandle:
        ...

    def call(
        self,
        spec: "CommandSpec",
    ) -> dict[str, Any]:
        ...


@dataclass(
    frozen=True
)
class CommandSpec:
    role: str
    argv: tuple[str, ...]
    cwd: str = ""
    environment: dict[str, str] | None = None
    sensitive_arguments: tuple[int, ...] = ()
    log_file: str = ""

    def public_info(
        self,
    ) -> dict[str, Any]:
        redacted = list(
            self.argv
        )

        for index in (
            self.sensitive_arguments
        ):
            if (
                index >= 0
                and index < len(redacted)
            ):
                redacted[index] = (
                    "<REDACTED>"
                )

        return {
            "role":
                self.role,
            "argv":
                redacted,
            "cwd":
                self.cwd,
            "environment_keys":
                sorted(
                    (
                        self.environment
                        or {}
                    ).keys()
                ),
            "log_file":
                self.log_file,
        }


def real_execution_enabled() -> bool:
    return (
        str(
            os.environ.get(
                REAL_EXECUTION_ENV,
                ""
            )
        ).strip()
        == "1"
    )


def require_real_execution() -> None:
    if not real_execution_enabled():
        raise RuntimeExecutionBlocked(
            "real_session_execution_disabled"
        )


class SubprocessCommandRunner:
    def __init__(
        self,
        *,
        require_gate: bool = True,
    ) -> None:
        if require_gate:
            require_real_execution()

    def spawn(
        self,
        spec: CommandSpec,
    ) -> CommandHandle:
        require_real_execution()

        import subprocess

        log_handle = None

        environment = (
            os.environ.copy()
        )

        environment.update(
            spec.environment
            or {}
        )

        try:
            if spec.log_file:
                log_path = Path(
                    spec.log_file
                )
                log_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                log_handle = log_path.open(
                    "ab"
                )

            return subprocess.Popen(
                list(spec.argv),
                cwd=(
                    spec.cwd
                    or None
                ),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=(
                    log_handle
                    or subprocess.DEVNULL
                ),
                stderr=(
                    subprocess.STDOUT
                    if log_handle
                    else subprocess.DEVNULL
                ),
                start_new_session=True,
            )
        finally:
            if log_handle:
                log_handle.close()

    def call(
        self,
        spec: CommandSpec,
    ) -> dict[str, Any]:
        require_real_execution()

        import subprocess

        environment = (
            os.environ.copy()
        )

        environment.update(
            spec.environment
            or {}
        )

        result = subprocess.run(
            list(spec.argv),
            cwd=(
                spec.cwd
                or None
            ),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        return {
            "returncode":
                int(
                    result.returncode
                ),
            "stdout":
                str(
                    result.stdout
                    or ""
                ),
            "stderr":
                str(
                    result.stderr
                    or ""
                ),
        }


def audio_modules_spec() -> CommandSpec:
    return CommandSpec(
        role="audio_modules",
        argv=(
            "pactl",
            "list",
            "short",
            "modules",
        ),
    )


def audio_sinks_spec() -> CommandSpec:
    return CommandSpec(
        role="audio_sinks",
        argv=(
            "pactl",
            "list",
            "short",
            "sinks",
        ),
    )


def audio_sink_inputs_spec() -> CommandSpec:
    return CommandSpec(
        role="audio_sink_inputs",
        argv=(
            "pactl",
            "list",
            "sink-inputs",
        ),
    )


def matching_audio_module_ids(
    output: object,
    sink_name: str,
) -> list[str]:
    sink_name = str(
        sink_name
        or ""
    ).strip()

    if not sink_name:
        return []

    expected = (
        "sink_name="
        + sink_name
    )

    result: list[str] = []

    for raw_line in str(
        output
        or ""
    ).splitlines():
        parts = raw_line.split(
            "\t"
        )

        if len(parts) < 3:
            continue

        module_id = (
            parts[0].strip()
        )
        module_name = (
            parts[1].strip()
        )
        arguments = (
            parts[2].strip()
        )

        if (
            module_name
            != "module-null-sink"
        ):
            continue

        if not module_id.isdigit():
            continue

        tokens = arguments.split()

        if expected not in tokens:
            continue

        result.append(
            module_id
        )

    return result


def audio_prepare_spec(
    identity: SessionIdentity,
) -> CommandSpec:
    return CommandSpec(
        role="audio_prepare",
        argv=(
            "pactl",
            "load-module",
            "module-null-sink",
            (
                "sink_name="
                + identity.audio_sink
            ),
            (
                "sink_properties="
                "device.description="
                + identity.audio_sink
            ),
            (
                "rate="
                + str(OUTPUT_AUDIO_RATE)
            ),
            "channels=2",
        ),
    )


def audio_remove_spec(
    module_id: str,
) -> CommandSpec:
    module_id = str(
        module_id
        or ""
    ).strip()

    if not module_id.isdigit():
        raise ValueError(
            "invalid_audio_module_id"
        )

    return CommandSpec(
        role="audio_remove",
        argv=(
            "pactl",
            "unload-module",
            module_id,
        ),
    )


def display_start_spec(
    *,
    display_value: str,
) -> CommandSpec:
    display_value = str(
        display_value
        or ""
    ).strip()

    if not display_value.startswith(
        ":"
    ):
        raise ValueError(
            "invalid_display_value"
        )

    return CommandSpec(
        role="display",
        argv=(
            "Xephyr",
            display_value,
            "-screen",
            f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
            "-ac",
            "-noreset",
        ),
    )


def game_start_spec(
    *,
    session_id: str,
    executable: str,
    server_url: str,
    display_value: str,
) -> CommandSpec:
    plan: GameLaunchPlan = (
        build_game_plan(
            session_id=session_id,
            executable=executable,
            server_url=server_url,
            display_value=display_value,
        )
    )

    return CommandSpec(
        role="game",
        argv=plan.argv,
        cwd=plan.cwd,
        environment=
            plan.environment,
        log_file=str(
            LOGS_DIR
            / "godot_game.log"
        ),
    )


def capture_start_spec(
    *,
    display_value: str,
    audio_monitor: str,
    destination_url: str,
    encoder: str,
    sink: str,
    bitrate_kbps: int,
    window_xid: int | None = None,
    output_width: int = OUTPUT_WIDTH,
    output_height: int = OUTPUT_HEIGHT,
    fps: int = OUTPUT_FPS,
    rtmp_no_ack_timeout: float = 65.0,
) -> CommandSpec:
    display_value = str(
        display_value
        or ""
    ).strip()

    audio_monitor = str(
        audio_monitor
        or ""
    ).strip()

    destination_url = str(
        destination_url
        or ""
    ).strip()

    encoder = str(
        encoder
        or ""
    ).strip()

    sink = str(
        sink
        or ""
    ).strip()

    bitrate_kbps = int(
        bitrate_kbps
    )
    output_width = max(
        320,
        min(
            3840,
            int(output_width),
        ),
    )
    output_height = max(
        320,
        min(
            3840,
            int(output_height),
        ),
    )
    fps = max(
        1,
        min(
            120,
            int(fps),
        ),
    )

    if not display_value.startswith(
        ":"
    ):
        raise ValueError(
            "invalid_display_value"
        )

    if not audio_monitor:
        raise ValueError(
            "audio_monitor_empty"
        )

    if not destination_url:
        raise ValueError(
            "destination_empty"
        )

    encoder_aliases = {
        "auto": "auto",
        "nvenc": "nvenc",
        "nvh264": "nvenc",
        "nvh264enc": "nvenc",
        "x264": "x264",
        "x264enc": "x264",
    }

    video_encoder = encoder_aliases.get(
        encoder,
        "",
    )

    if video_encoder not in {
        "auto",
        "nvenc",
        "x264",
    }:
        raise ValueError(
            "unsupported_encoder"
        )

    if sink not in {
        "rtmp2sink",
        "rtmpsink",
    }:
        raise ValueError(
            "unsupported_sink"
        )

    if bitrate_kbps < 500:
        raise ValueError(
            "invalid_bitrate"
        )

    capture_script = (
        PROJECT_DIR
        / "scripts"
        / "gst_html_capture_pipeline.py"
    )

    argv: list[str] = [
        sys.executable,
        str(capture_script),
        "--display",
        display_value,
        "--audio-source",
        audio_monitor,
        "--video-bitrate",
        str(
            bitrate_kbps
        ),
        "--output-width",
        str(
            output_width
        ),
        "--output-height",
        str(
            output_height
        ),
        "--fps",
        str(
            fps
        ),
        "--audio-rate",
        str(
            OUTPUT_AUDIO_RATE
        ),
        "--audio-bitrate",
        str(
            OUTPUT_AUDIO_BITRATE
        ),
        "--video-encoder",
        video_encoder,
        "--rtmp-sink",
        sink,
        "--metrics-file",
        str(
            OUTPUT_METRICS_FILE
        ),
        "--rtmp-no-ack-timeout",
        str(
            max(
                5.0,
                float(rtmp_no_ack_timeout),
            )
        ),
        "--rtmp-no-ack-min-bytes",
        "5000000",
        "--rtmp-stale-ack-timeout",
        "45",
        "--rtmp-stale-ack-min-bytes",
        "30000000",
        "--rtmp-restart-max",
        "0",
    ]

    if (
        window_xid is not None
        and int(window_xid) > 0
    ):
        argv.extend(
            [
                "--window-xid",
                str(
                    int(window_xid)
                ),
            ]
        )

    argv.extend(
        [
            "--rtmp-url",
            destination_url,
        ]
    )

    sensitive_index = (
        len(argv)
        - 1
    )

    return CommandSpec(
        role="capture",
        argv=tuple(
            argv
        ),
        sensitive_arguments=(
            sensitive_index,
        ),
        log_file=str(
            OUTPUT_LOG_FILE
        ),
    )


def monitor_start_call(
    *,
    username: str,
    start_callable: Callable[
        ...,
        dict[str, Any],
    ],
) -> dict[str, Any]:
    require_real_execution()

    username = str(
        username
        or ""
    ).strip()

    if not username:
        raise ValueError(
            "username_empty"
        )

    state = start_callable(
        username=username,
        prepare_local_node=True,
    )

    return state


def monitor_stop_call(
    *,
    stop_callable: Callable[
        ...,
        dict[str, Any],
    ],
) -> dict[str, Any]:
    require_real_execution()

    state = stop_callable(
        stop_local_node_runtime=True,
    )

    result = (
        dict(state)
        if isinstance(
            state,
            dict,
        )
        else {}
    )

    monitor_stopped = (
        not bool(
            result.get(
                "running"
            )
        )
        and not bool(
            result.get(
                "connected"
            )
        )
        and not bool(
            result.get(
                "listening"
            )
        )
    )

    result["ok"] = (
        monitor_stopped
    )

    result["stopped"] = (
        monitor_stopped
    )

    return result


def public_runtime_capabilities() -> dict[str, Any]:
    return {
        "real_execution_enabled":
            real_execution_enabled(),
        "gate_environment":
            REAL_EXECUTION_ENV,
        "game_dir":
            str(GAME_DIR),
        "resolution": {
            "width": OUTPUT_WIDTH,
            "height": OUTPUT_HEIGHT,
        },
        "audio": {
            "rate": OUTPUT_AUDIO_RATE,
            "channels": 2,
        },
    }


def build_all_specs_preview(
    *,
    session_id: str,
    executable: str,
    server_url: str,
    display_value: str,
    destination_url: str,
    encoder: str,
    sink: str,
    bitrate_kbps: int,
) -> dict[str, Any]:
    identity = build_identity(
        session_id
    )

    specs_list: list[CommandSpec] = [
        audio_prepare_spec(
            identity
        ),
    ]

    if (
        str(display_value).strip()
        != ":0"
    ):
        specs_list.append(
            display_start_spec(
                display_value=
                    display_value,
            )
        )

    specs_list.extend(
        [
            game_start_spec(
                session_id=
                    identity.session_id,
                executable=
                    executable,
                server_url=
                    server_url,
                display_value=
                    display_value,
            ),
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
                window_xid=1,
            ),
        ]
    )

    specs = tuple(
        specs_list
    )

    return {
        "execution": False,
        "identity":
            identity.public_info(),
        "specs": [
            spec.public_info()
            for spec in specs
        ],
    }
