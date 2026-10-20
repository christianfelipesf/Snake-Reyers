from __future__ import annotations

import random
import threading
from pathlib import Path
from typing import Any

from cobrinha_server.core.json_store import (
    read_json,
    write_json_atomic,
)
from cobrinha_server.core.settings import (
    ASSETS_DIR,
    RUNS_DIR,
)


BACKGROUND_MUSIC_DIR = (
    ASSETS_DIR
    / "music"
    / "background"
)
MUSIC_RUNTIME_FILE = (
    RUNS_DIR
    / "music_runtime.json"
)
SUPPORTED_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
}
DEFAULT_VOLUME = 0.16

_LOCK = threading.Lock()


def _clamp_volume(
    value: object,
) -> float:
    try:
        number = float(value)
    except (
        TypeError,
        ValueError,
    ):
        number = DEFAULT_VOLUME

    return max(
        0.0,
        min(
            1.0,
            number,
        ),
    )


def _track_title(
    path: Path,
) -> str:
    return path.stem.replace("_", " ").strip() or path.name


def track_entries() -> list[dict[str, Any]]:
    if not BACKGROUND_MUSIC_DIR.is_dir():
        return []

    result: list[dict[str, Any]] = []

    for path in sorted(
        BACKGROUND_MUSIC_DIR.rglob("*"),
        key=lambda item: str(
            item.relative_to(
                BACKGROUND_MUSIC_DIR
            )
        ).casefold(),
    ):
        if (
            not path.is_file()
            or path.name.startswith(".")
            or path.suffix.casefold()
            not in SUPPORTED_EXTENSIONS
        ):
            continue

        source_path = str(
            path.resolve()
        )
        result.append(
            {
                "path": source_path,
                "source_path": source_path,
                "title": _track_title(path),
                "processed": False,
            }
        )

    return result


def tracks() -> list[str]:
    return [
        str(
            item["path"]
        )
        for item in track_entries()
    ]


def track_metadata(
    entries: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}

    for entry in (
        entries
        if entries is not None
        else track_entries()
    ):
        track_path = str(
            entry.get("path")
            or ""
        )
        if not track_path:
            continue

        metadata[track_path] = {
            "title": str(
                entry.get("title")
                or Path(track_path).stem
            ),
            "source_path": str(
                entry.get("source_path")
                or ""
            ),
            "processed": False,
        }

    return metadata


def _read() -> dict[str, Any]:
    raw = read_json(
        MUSIC_RUNTIME_FILE,
        {},
    )

    if not isinstance(
        raw,
        dict,
    ):
        raw = {}

    entries = track_entries()
    available_tracks = [
        str(
            item["path"]
        )
        for item in entries
    ]

    current_track = str(
        raw.get("current_track")
        or ""
    ).strip()

    if current_track not in available_tracks:
        current_track = (
            available_tracks[0]
            if available_tracks
            else ""
        )

    return {
        "enabled": bool(
            raw.get(
                "enabled",
                True,
            )
        ),
        "volume": _clamp_volume(
            raw.get(
                "volume",
                DEFAULT_VOLUME,
            )
        ),
        "current_track": current_track,
        "tracks": available_tracks,
        "track_metadata": track_metadata(entries),
    }


def _persist(
    state: dict[str, Any],
) -> None:
    write_json_atomic(
        MUSIC_RUNTIME_FILE,
        {
            "enabled": bool(
                state.get("enabled")
            ),
            "volume": _clamp_volume(
                state.get("volume")
            ),
            "current_track": str(
                state.get("current_track")
                or ""
            ),
        },
    )


def status() -> dict[str, Any]:
    with _LOCK:
        state = _read()

    return {
        **state,
        "track_count": len(
            state["tracks"]
        ),
    }


def update(
    *,
    volume: object | None = None,
    enabled: object | None = None,
    current_track: object | None = None,
) -> dict[str, Any]:
    with _LOCK:
        state = _read()

        if volume is not None:
            state["volume"] = _clamp_volume(
                volume
            )

        if enabled is not None:
            state["enabled"] = bool(
                enabled
            )

        if current_track is not None:
            candidate = str(
                current_track
                or ""
            ).strip()

            if candidate in state["tracks"]:
                state["current_track"] = candidate

        _persist(state)

    return status()


def choose_session_start_track() -> dict[str, Any]:
    with _LOCK:
        state = _read()
        available_tracks = list(
            state["tracks"]
        )

        if available_tracks:
            current_track = str(
                state.get("current_track")
                or ""
            )
            candidates = [
                track
                for track in available_tracks
                if track != current_track
            ]

            if not candidates:
                candidates = available_tracks

            state["current_track"] = random.choice(
                candidates
            )

        _persist(state)

    return status()


def websocket_message() -> dict[str, Any]:
    return {
        "type": "music_runtime",
        "payload": status(),
    }
