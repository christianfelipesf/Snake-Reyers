#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path


SERVER_DIR = Path(
    os.getenv(
        "COBRINHA_SERVER_DIR",
        str(Path(__file__).resolve().parents[1]),
    )
).resolve()

GAME_DIR = Path(
    os.getenv(
        "SNAKE_REYERS_GAME_SOURCE",
        str(SERVER_DIR / "game-source-unavailable"),
    )
).resolve()

BUILD_GAME_DIR = (
    SERVER_DIR.parent
    / "game"
    / ("windows" if os.name == "nt" else "linux")
).resolve()

BUILD_GAME_EXECUTABLE = (
    BUILD_GAME_DIR
    / (
        "SnakeReyers.exe"
        if os.name == "nt"
        else "SnakeReyers.x86_64"
    )
)

MONITOR_DIR = (
    SERVER_DIR
    / "external"
    / "tiktok-live-monitoring-server"
).resolve()

MONITOR_ENTRY = (
    MONITOR_DIR
    / "server.js"
).resolve()

TERM_TIMEOUT_SECONDS = 5.0

STALE_PID_FILES = (
    SERVER_DIR / "runs" / "server.pid",
    SERVER_DIR / "runs" / "tiktok-live-monitor.pid",
)


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    cwd: Path | None
    argv: tuple[str, ...]
    role: str


def _argv(pid: int) -> tuple[str, ...]:
    data = (
        Path("/proc")
        / str(pid)
        / "cmdline"
    ).read_bytes()

    return tuple(
        item.decode(
            "utf-8",
            errors="replace",
        )
        for item in data.split(b"\x00")
        if item
    )


def _cwd(pid: int) -> Path | None:
    try:
        return (
            Path("/proc")
            / str(pid)
            / "cwd"
        ).resolve()
    except OSError:
        return None


def _ppid(pid: int) -> int:
    text = (
        Path("/proc")
        / str(pid)
        / "status"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    for line in text.splitlines():
        if line.startswith("PPid:"):
            return int(
                line.split(
                    ":",
                    1,
                )[1].strip()
            )

    return 0


def _resolved_arg_path(
    value: str,
    cwd: Path | None,
) -> Path | None:
    text = str(value or "").strip()

    if not text:
        return None

    path = Path(text)

    if not path.is_absolute():
        if cwd is None:
            return None

        path = cwd / path

    try:
        return path.resolve()
    except OSError:
        return None


def _is_backend(
    cwd: Path | None,
    argv: tuple[str, ...],
) -> bool:
    return (
        cwd == SERVER_DIR
        and len(argv) >= 4
        and argv[1] == "-m"
        and argv[2] == "uvicorn"
        and argv[3]
        == "cobrinha_server.main:app"
        and (
            Path(argv[0]).name
            in {
                "python",
                "python3",
            }
            or argv[0].endswith(
                "/.venv/bin/python"
            )
        )
    )


def _is_preview(
    cwd: Path | None,
    argv: tuple[str, ...],
) -> bool:
    return (
        cwd == GAME_DIR
        and "--cobrinha-preview"
        in argv
        and bool(argv)
        and "godot"
        in Path(argv[0]).name.casefold()
    )


def _is_official_game(
    cwd: Path | None,
    argv: tuple[str, ...],
) -> bool:
    if (
        "--cobrinha-live"
        not in argv
        or not argv
    ):
        return False

    executable = (
        Path(argv[0])
        .name
        .casefold()
    )

    if (
        cwd == GAME_DIR
        and "godot" in executable
    ):
        return True

    return (
        cwd == BUILD_GAME_DIR
        or executable.startswith(
            "cobrinha_live"
        )
    )


def _is_monitor_node(
    cwd: Path | None,
    argv: tuple[str, ...],
) -> bool:
    if cwd != MONITOR_DIR:
        return False

    if not argv:
        return False

    executable = (
        Path(argv[0])
        .name
        .casefold()
    )

    node_index: int | None = None

    if executable in {
        "node",
        "nodejs",
    }:
        node_index = 0

    elif executable in {
        "torsocks",
    }:
        for index, item in enumerate(
            argv[1:4],
            1,
        ):
            if (
                Path(item)
                .name
                .casefold()
                in {
                    "node",
                    "nodejs",
                }
            ):
                node_index = index
                break

    if node_index is None:
        return False

    entry_index = node_index + 1

    if entry_index >= len(argv):
        return False

    entry = _resolved_arg_path(
        argv[entry_index],
        cwd,
    )

    return entry == MONITOR_ENTRY


def _is_capture(
    cwd: Path | None,
    argv: tuple[str, ...],
) -> bool:
    if (
        cwd != SERVER_DIR
        or not argv
    ):
        return False

    executable = (
        Path(argv[0])
        .name
        .casefold()
    )

    if executable != "gst-launch-1.0":
        return False

    args = {
        str(item).strip().casefold()
        for item in argv[1:]
    }

    has_ximagesrc = (
        "ximagesrc"
        in args
    )

    has_pulsesrc = (
        "pulsesrc"
        in args
    )

    has_flvmux = (
        "flvmux"
        in args
    )

    has_video_shape = any(
        item.startswith(
            "video/x-raw,"
        )
        and "width=720" in item
        and "height=1280" in item
        and "framerate=30/1"
        in item
        for item in args
    )

    has_audio_shape = any(
        item.startswith(
            "audio/x-raw,"
        )
        and "rate=48000" in item
        and "channels=2" in item
        for item in args
    )

    has_sink = (
        "rtmp2sink" in args
        or "rtmpsink" in args
    )

    return (
        has_ximagesrc
        and has_pulsesrc
        and has_flvmux
        and has_video_shape
        and has_audio_shape
        and has_sink
    )


def _is_display(
    cwd: Path | None,
    argv: tuple[str, ...],
) -> bool:
    return (
        cwd == SERVER_DIR
        and bool(argv)
        and Path(argv[0]).name
        == "Xephyr"
    )


def classify(
    cwd: Path | None,
    argv: tuple[str, ...],
) -> str:
    if _is_backend(
        cwd,
        argv,
    ):
        return "backend"

    if _is_preview(
        cwd,
        argv,
    ):
        return "preview"

    if _is_official_game(
        cwd,
        argv,
    ):
        return "official_game"

    if _is_monitor_node(
        cwd,
        argv,
    ):
        return "monitor_node"

    if _is_capture(
        cwd,
        argv,
    ):
        return "capture"

    if _is_display(
        cwd,
        argv,
    ):
        return "display"

    return ""


def ancestor_pids() -> set[int]:
    result: set[int] = set()
    current = os.getpid()

    while (
        current > 1
        and current not in result
    ):
        result.add(current)

        try:
            current = _ppid(current)
        except (
            FileNotFoundError,
            PermissionError,
            ProcessLookupError,
            OSError,
            ValueError,
        ):
            break

    result.add(os.getpid())
    result.add(os.getppid())

    return result


def discover() -> list[ProcessInfo]:
    protected = ancestor_pids()
    found: list[ProcessInfo] = []

    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue

        pid = int(proc.name)

        if pid in protected:
            continue

        try:
            argv = _argv(pid)
            cwd = _cwd(pid)
            ppid = _ppid(pid)
        except (
            FileNotFoundError,
            PermissionError,
            ProcessLookupError,
            OSError,
            ValueError,
        ):
            continue

        role = classify(
            cwd,
            argv,
        )

        if not role:
            continue

        found.append(
            ProcessInfo(
                pid=pid,
                ppid=ppid,
                cwd=cwd,
                argv=argv,
                role=role,
            )
        )

    return sorted(
        found,
        key=lambda item:
            (
                item.role,
                item.pid,
            ),
    )


def alive(pid: int) -> bool:
    try:
        os.kill(
            pid,
            0,
        )
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    return True


def remove_stale_pid_files() -> None:
    for path in STALE_PID_FILES:
        if not path.exists():
            continue

        try:
            raw = path.read_text(
                encoding="utf-8",
                errors="replace",
            ).strip()

            pid = int(raw)

        except (
            OSError,
            ValueError,
        ):
            pid = 0

        if (
            pid > 0
            and alive(pid)
        ):
            continue

        try:
            path.unlink()
            print(
                "STALE_PID_REMOVED="
                f"{path}"
            )
        except FileNotFoundError:
            pass


def apply_cleanup(
    items: list[ProcessInfo],
) -> None:
    protected = ancestor_pids()

    targets = [
        item
        for item in items
        if item.pid not in protected
    ]

    for item in targets:
        print(
            "TERM "
            f"role={item.role} "
            f"pid={item.pid}"
        )

        try:
            os.kill(
                item.pid,
                signal.SIGTERM,
            )
        except ProcessLookupError:
            pass

    deadline = (
        time.monotonic()
        + TERM_TIMEOUT_SECONDS
    )

    while (
        time.monotonic()
        < deadline
    ):
        remaining = [
            item
            for item in targets
            if alive(item.pid)
        ]

        if not remaining:
            break

        time.sleep(0.10)

    for item in targets:
        if not alive(item.pid):
            continue

        print(
            "KILL "
            f"role={item.role} "
            f"pid={item.pid}"
        )

        try:
            os.kill(
                item.pid,
                signal.SIGKILL,
            )
        except ProcessLookupError:
            pass

    remove_stale_pid_files()


def self_test() -> None:
    tests = [
        (
            SERVER_DIR,
            (
                str(
                    SERVER_DIR
                    / ".venv"
                    / "bin"
                    / "python"
                ),
                "-m",
                "uvicorn",
                "cobrinha_server.main:app",
            ),
            "backend",
        ),
        (
            GAME_DIR,
            (
                "godot",
                "--path",
                str(GAME_DIR),
                "--",
                "--cobrinha-preview",
            ),
            "preview",
        ),
        (
            GAME_DIR,
            (
                "godot",
                "--path",
                str(GAME_DIR),
                "--",
                "--cobrinha-live",
            ),
            "official_game",
        ),
        (
            BUILD_GAME_DIR,
            (
                str(
                    BUILD_GAME_EXECUTABLE
                ),
                "--windowed",
                "--resolution",
                "720x1280",
                "--",
                "--cobrinha-live",
            ),
            "official_game",
        ),
        (
            MONITOR_DIR,
            (
                "node",
                str(MONITOR_ENTRY),
            ),
            "monitor_node",
        ),
        (
            MONITOR_DIR,
            (
                "torsocks",
                "node",
                str(MONITOR_ENTRY),
            ),
            "monitor_node",
        ),
        (
            SERVER_DIR,
            (
                "gst-launch-1.0",
                "-e",
                "ximagesrc",
                "display-name=:99",
                "remote=true",
                "use-damage=false",
                "show-pointer=false",
                "!",
                "videoconvert",
                "!",
                "videoscale",
                "!",
                "videorate",
                "!",
                (
                    "video/x-raw,"
                    "width=720,"
                    "height=1280,"
                    "framerate=30/1"
                ),
                "!",
                "x264enc",
                "bitrate=2500",
                "!",
                "h264parse",
                "!",
                "queue",
                "!",
                "mux.",
                "pulsesrc",
                "device=cobrinha_test.monitor",
                "!",
                "audioconvert",
                "!",
                "audioresample",
                "!",
                "audiorate",
                "!",
                (
                    "audio/x-raw,"
                    "rate=48000,"
                    "channels=2"
                ),
                "!",
                "voaacenc",
                "bitrate=160000",
                "!",
                "queue",
                "!",
                "mux.",
                "flvmux",
                "name=mux",
                "streamable=true",
                "!",
                "queue",
                "!",
                "rtmp2sink",
                "location=<REDACTED>",
                "sync=true",
            ),
            "capture",
        ),
        (
            SERVER_DIR,
            (
                "bash",
                "-lc",
                (
                    "grep gst_html_capture_pipeline "
                    "gst-launch-1.0 ximagesrc "
                    "pulsesrc flvmux rtmp2sink"
                ),
            ),
            "",
        ),
        (
            SERVER_DIR,
            (
                "gst-launch-1.0",
                "videotestsrc",
                "!",
                "fakesink",
            ),
            "",
        ),
        (
            SERVER_DIR,
            (
                "Xephyr",
                ":99",
            ),
            "display",
        ),
        (
            SERVER_DIR,
            (
                "bash",
                "-lc",
                (
                    "texto contendo "
                    "tiktok-live-monitoring-server "
                    "mas sendo apenas o Runner"
                ),
            ),
            "",
        ),
        (
            Path(
                "/opt/legacy-game"
            ),
            (
                "node",
                str(
                    Path(
                        "/opt/legacy-game/external/"
                        "tiktok-live-monitoring-server/"
                        "server.js"
                    )
                ),
            ),
            "",
        ),
        (
            Path("/tmp"),
            (
                "python3",
                "qualquer_coisa.py",
            ),
            "",
        ),
    ]

    for index, (
        cwd,
        argv,
        expected,
    ) in enumerate(
        tests,
        1,
    ):
        actual = classify(
            cwd,
            argv,
        )

        print(
            f"SELF_TEST_{index}="
            f"{actual or 'ignored'}"
        )

        if actual != expected:
            raise AssertionError(
                {
                    "index": index,
                    "actual": actual,
                    "expected": expected,
                }
            )

    print("SELF_TEST_OK=1")


def main() -> int:
    parser = argparse.ArgumentParser()

    group = (
        parser.add_mutually_exclusive_group(
            required=True
        )
    )

    group.add_argument(
        "--dry-run",
        action="store_true",
    )

    group.add_argument(
        "--apply",
        action="store_true",
    )

    group.add_argument(
        "--self-test",
        action="store_true",
    )

    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    items = discover()

    print(
        "CLEAN_START_TARGET_COUNT="
        f"{len(items)}"
    )

    for item in items:
        executable = (
            Path(item.argv[0]).name
            if item.argv
            else ""
        )

        print(
            "TARGET "
            f"role={item.role} "
            f"pid={item.pid} "
            f"ppid={item.ppid} "
            f"exec={executable}"
        )

    if args.dry_run:
        print(
            "CLEAN_START_DRY_RUN=1"
        )
        return 0

    apply_cleanup(items)

    remaining = discover()

    if remaining:
        for item in remaining:
            print(
                "REMAINING "
                f"role={item.role} "
                f"pid={item.pid}"
            )

        return 2

    print(
        "CLEAN_START_APPLIED=1"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
