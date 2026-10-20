from __future__ import annotations

import importlib.util
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

from cobrinha_server.core.json_store import (
    read_json,
    write_json_atomic,
)
from cobrinha_server.core.settings import (
    ASSETS_DIR,
    LOGS_DIR,
    RUNS_DIR,
)
from cobrinha_server.services.audio_timeline import (
    write_audio_timeline_json,
)


MUSIC_RUNTIME_FILE = (
    RUNS_DIR
    / "music_runtime.json"
)

BACKGROUND_MUSIC_DIR = (
    ASSETS_DIR
    / "music"
    / "background"
)

BACKGROUND_MUSIC_PROCESSED_DIR = (
    ASSETS_DIR
    / "music"
    / "background_processed"
)

BACKGROUND_DEMUX_RUNS_DIR = (
    RUNS_DIR
    / "demucs_background"
)

BACKGROUND_PROCESS_LOG_FILE = (
    LOGS_DIR
    / "background_music_processing.log"
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

UUID_SUFFIX_RE = re.compile(
    r"\s*\[[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}\]\s*"
)

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


def tracks() -> list[str]:
    return [
        str(
            item["path"]
        )
        for item in track_entries()
    ]


def track_entries() -> list[dict[str, Any]]:
    if not BACKGROUND_MUSIC_DIR.is_dir():
        return []

    processed_by_source = _processed_tracks_by_source()
    result: list[dict[str, Any]] = []

    for path in sorted(
            BACKGROUND_MUSIC_DIR.iterdir(),
            key=lambda item:
                item.name.casefold(),
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
        processed = processed_by_source.get(
            source_path,
            {},
        )

        if processed:
            result.append(
                processed
            )
        else:
            result.append(
                {
                    "path": source_path,
                    "source_path": source_path,
                    "title": _track_title(path),
                    "processed": False,
                }
            )

    return result


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

        item = {
            "title":
                str(
                    entry.get("title")
                    or Path(track_path).stem
                ),
            "source_path":
                str(
                    entry.get("source_path")
                    or ""
                ),
            "processed":
                bool(
                    entry.get("processed")
                ),
        }

        for key in (
            "vocal_path",
            "instrumental_path",
            "timeline_path",
            "timeline_end",
        ):
            if key in entry:
                item[key] = entry[key]

        metadata[track_path] = item

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

    if (
        current_track
        not in available_tracks
    ):
        current_track = (
            available_tracks[0]
            if available_tracks
            else ""
        )

    return {
        "enabled":
            bool(
                raw.get(
                    "enabled",
                    True,
                )
            ),
        "volume":
            _clamp_volume(
                raw.get(
                    "volume",
                    DEFAULT_VOLUME,
                )
            ),
        "current_track":
            current_track,
        "tracks":
            available_tracks,
        "track_metadata":
            track_metadata(entries),
    }


def status() -> dict[str, Any]:
    with _LOCK:
        state = _read()

    return {
        **state,
        "track_count":
            len(
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
            state["volume"] = (
                _clamp_volume(
                    volume
                )
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
                state["current_track"] = (
                    candidate
                )

        write_json_atomic(
            MUSIC_RUNTIME_FILE,
            {
                "enabled":
                    state["enabled"],
                "volume":
                    state["volume"],
        "current_track":
                    state[
                        "current_track"
                    ],
            },
        )

    return status()


def choose_session_start_track() -> dict[str, Any]:
    with _LOCK:
        state = _read()
        available_tracks = list(
            state["tracks"]
        )

        if available_tracks:
            current_track = str(
                state.get(
                    "current_track",
                    "",
                )
                or ""
            )
            candidates = [
                track
                for track in available_tracks
                if track != current_track
            ]

            if not candidates:
                candidates = available_tracks

            state["current_track"] = (
                random.choice(candidates)
            )

        write_json_atomic(
            MUSIC_RUNTIME_FILE,
            {
                "enabled":
                    state["enabled"],
                "volume":
                    state["volume"],
                "current_track":
                    state[
                        "current_track"
                    ],
            },
        )

    return status()


def websocket_message() -> dict[str, Any]:
    return {
        "type": "music_runtime",
        "payload": status(),
    }


def demucs_available() -> bool:
    return (
        importlib.util.find_spec(
            "demucs"
        )
        is not None
    )


def ffmpeg_available() -> bool:
    return shutil.which(
        "ffmpeg"
    ) is not None


def sanitize_background_filenames() -> list[dict[str, str]]:
    if not BACKGROUND_MUSIC_DIR.is_dir():
        return []

    changes: list[dict[str, str]] = []

    for path in sorted(
        BACKGROUND_MUSIC_DIR.iterdir(),
        key=lambda item:
            item.name.casefold(),
    ):
        if (
            not path.is_file()
            or path.name.startswith(".")
            or path.suffix.casefold()
            not in SUPPORTED_EXTENSIONS
        ):
            continue

        clean_stem = _sanitize_track_stem(
            path.stem
        )
        target = path.with_name(
            clean_stem
            + path.suffix.casefold()
        )
        target = _unique_path(
            target,
            path,
        )

        if target == path:
            continue

        path.rename(target)
        changes.append(
            {
                "from": str(path),
                "to": str(target),
            }
        )

    return changes


def process_all_background_tracks(
    *,
    force: bool = False,
) -> dict[str, Any]:
    _ensure_processing_dirs()

    if not demucs_available():
        raise RuntimeError(
            "Demucs nao esta instalado no .venv."
        )

    if not ffmpeg_available():
        raise RuntimeError(
            "ffmpeg nao esta disponivel no sistema."
        )

    renamed = sanitize_background_filenames()
    processed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for source in _source_audio_files():
        try:
            result = process_background_track(
                source,
                force=force,
            )
        except Exception as exc:
            failed.append(
                {
                    "source_path": str(source),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        if bool(
            result.get("already_ready")
        ):
            skipped.append(result)
        else:
            processed.append(result)

    return {
        "renamed": renamed,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
    }


def process_background_track(
    source: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(
            str(source)
        )

    song_id = _safe_slug(
        source.stem
    )
    output_dir = (
        BACKGROUND_MUSIC_PROCESSED_DIR
        / song_id
    )
    manifest_path = (
        output_dir
        / "manifest.json"
    )

    if (
        not force
        and _processed_manifest_ready(
            manifest_path
        )
    ):
        manifest = read_json(
            manifest_path,
            {},
        )
        if isinstance(
            manifest,
            dict,
        ):
            manifest["already_ready"] = True
            return manifest

    demucs_dir = (
        BACKGROUND_DEMUX_RUNS_DIR
        / song_id
    )

    shutil.rmtree(
        demucs_dir,
        ignore_errors=True,
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    _run_logged(
        [
            sys.executable,
            "-m",
            "demucs",
            "--two-stems",
            "vocals",
            "-n",
            "htdemucs",
            "-o",
            str(demucs_dir),
            str(source),
        ]
    )

    raw_vocal = _find_demucs_file(
        demucs_dir,
        "vocals.wav",
    )
    raw_instrumental = _find_demucs_file(
        demucs_dir,
        "no_vocals.wav",
    )

    vocal_path = output_dir / "vocals.wav"
    instrumental_path = (
        output_dir
        / "instrumental.wav"
    )
    timeline_path = (
        output_dir
        / "vocal_timeline.json"
    )

    _convert_to_pcm_wav(
        raw_vocal,
        vocal_path,
    )
    _convert_to_pcm_wav(
        raw_instrumental,
        instrumental_path,
    )

    write_audio_timeline_json(
        vocal_path,
        timeline_path,
        window_ms=45,
        silence_threshold=0.018,
        micro_pause_max=0.22,
        min_speech_ms=80,
        min_pause_ms=45,
    )

    timeline = read_json(
        timeline_path,
        {},
    )
    if not isinstance(
        timeline,
        dict,
    ):
        timeline = {}

    manifest = {
        "id": song_id,
        "kind": "background_music",
        "title": _track_title(source),
        "source_path": str(
            source.resolve()
        ),
        "created_at": time.time(),
        "duration": float(
            timeline.get(
                "timeline_end",
                0.0,
            )
            or 0.0
        ),
        "files": {
            "vocal": str(
                vocal_path.resolve()
            ),
            "instrumental": str(
                instrumental_path.resolve()
            ),
            "timeline": str(
                timeline_path.resolve()
            ),
        },
    }

    write_json_atomic(
        manifest_path,
        manifest,
    )
    return manifest


def _processed_tracks_by_source() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    if not BACKGROUND_MUSIC_PROCESSED_DIR.is_dir():
        return result

    for manifest_path in sorted(
        BACKGROUND_MUSIC_PROCESSED_DIR.glob(
            "*/manifest.json"
        ),
        key=lambda item:
            item.parent.name.casefold(),
    ):
        manifest = read_json(
            manifest_path,
            {},
        )
        if not isinstance(
            manifest,
            dict,
        ):
            continue

        files = manifest.get(
            "files",
            {},
        )
        if not isinstance(
            files,
            dict,
        ):
            continue

        instrumental_path = _manifest_file_path(
            manifest_path,
            files,
            "instrumental",
            "instrumental.wav",
        )
        vocal_path = _manifest_file_path(
            manifest_path,
            files,
            "vocal",
            "vocals.wav",
        )
        timeline_path = _manifest_file_path(
            manifest_path,
            files,
            "timeline",
            "vocal_timeline.json",
        )
        source_path = _manifest_source_path(
            manifest,
            manifest_path,
        )

        if (
            instrumental_path is None
            or vocal_path is None
            or timeline_path is None
            or source_path is None
        ):
            continue

        key = str(source_path)
        result[key] = {
            "path": key,
            "source_path": key,
            "title": str(
                manifest.get(
                    "title",
                    source_path.stem,
                )
            ),
            "processed": True,
            "vocal_path": str(
                vocal_path
            ),
            "instrumental_path": str(
                instrumental_path
            ),
            "timeline_path": str(
                timeline_path
            ),
            "timeline_end": float(
                manifest.get(
                    "duration",
                    0.0,
                )
                or 0.0
            ),
        }

    return result


def _source_audio_files() -> list[Path]:
    if not BACKGROUND_MUSIC_DIR.is_dir():
        return []

    return [
        path
        for path in sorted(
            BACKGROUND_MUSIC_DIR.iterdir(),
            key=lambda item:
                item.name.casefold(),
        )
        if (
            path.is_file()
            and not path.name.startswith(".")
            and path.suffix.casefold()
            in SUPPORTED_EXTENSIONS
        )
    ]


def _processed_manifest_ready(
    manifest_path: Path,
) -> bool:
    manifest = read_json(
        manifest_path,
        {},
    )
    if not isinstance(
        manifest,
        dict,
    ):
        return False

    files = manifest.get(
        "files",
        {},
    )
    if not isinstance(
        files,
        dict,
    ):
        return False

    return all(
        _manifest_file_path(
            manifest_path,
            files,
            key,
            fallback,
        )
        is not None
        for key, fallback in (
            ("vocal", "vocals.wav"),
            ("instrumental", "instrumental.wav"),
            ("timeline", "vocal_timeline.json"),
        )
    )


def _manifest_file_path(
    manifest_path: Path,
    files: dict[str, Any],
    key: str,
    fallback_name: str,
) -> Path | None:
    local = manifest_path.parent / fallback_name
    if local.is_file():
        return local.resolve()

    configured = Path(
        str(
            files.get(key)
            or ""
        )
    ).expanduser()

    if configured.is_file():
        return configured.resolve()

    return None


def _manifest_source_path(
    manifest: dict[str, Any],
    manifest_path: Path,
) -> Path | None:
    song_id = str(
        manifest.get("id")
        or manifest_path.parent.name
    )

    for source in _source_audio_files():
        if _safe_slug(source.stem) == song_id:
            return source.resolve()

    configured = Path(
        str(
            manifest.get("source_path")
            or ""
        )
    ).expanduser()

    if configured.is_file():
        return configured.resolve()

    return None


def _ensure_processing_dirs() -> None:
    for path in (
        BACKGROUND_MUSIC_DIR,
        BACKGROUND_MUSIC_PROCESSED_DIR,
        BACKGROUND_DEMUX_RUNS_DIR,
        LOGS_DIR,
    ):
        path.mkdir(
            parents=True,
            exist_ok=True,
        )


def _safe_slug(value: str) -> str:
    normalized = (
        unicodedata.normalize(
            "NFKD",
            value,
        )
        .encode(
            "ascii",
            "ignore",
        )
        .decode(
            "ascii",
        )
        .lower()
    )

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        normalized,
    ).strip("-")

    return slug or "musica"


def _sanitize_track_stem(stem: str) -> str:
    clean = UUID_SUFFIX_RE.sub(
        "",
        stem,
    ).strip()
    clean = (
        clean.replace("’", "'")
        .replace("‘", "'")
        .replace("“", "")
        .replace("”", "")
        .replace('"', "")
    )
    clean = re.sub(
        r"\s+",
        " ",
        clean,
    ).strip()
    return clean or _safe_slug(stem)


def _unique_path(
    target: Path,
    original: Path,
) -> Path:
    if (
        target == original
        or not target.exists()
    ):
        return target

    counter = 2
    while True:
        candidate = target.with_name(
            f"{target.stem}-{counter}{target.suffix}"
        )
        if (
            candidate == original
            or not candidate.exists()
        ):
            return candidate
        counter += 1


def _track_title(path: Path) -> str:
    return (
        _sanitize_track_stem(path.stem)
        .replace("-", " ")
        .strip()
        .title()
    )


def _run_logged(
    command: list[str],
    *,
    cwd: Path | None = None,
) -> None:
    LOGS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    with BACKGROUND_PROCESS_LOG_FILE.open(
        "a",
        encoding="utf-8",
    ) as log:
        log.write(
            "\n\n$ "
            + " ".join(command)
            + "\n"
        )
        log.flush()

        subprocess.run(
            command,
            cwd=(
                str(cwd)
                if cwd is not None
                else None
            ),
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )


def _find_demucs_file(
    root: Path,
    name: str,
) -> Path:
    for path in root.rglob(name):
        if path.is_file():
            return path

    raise FileNotFoundError(
        f"Demucs nao gerou {name}."
    )


def _convert_to_pcm_wav(
    source: Path,
    target: Path,
) -> None:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    _run_logged(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-sample_fmt",
            "s16",
            str(target),
        ]
    )
