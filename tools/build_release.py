#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT.parent / "release-assets" / "packages"
ARCHIVE_ROOT = "SnakeReyers"
AUDIO_SOURCE = Path(
    os.getenv(
        "SNAKE_REYERS_AUDIO_SOURCE",
        str(ROOT.parent / "audio-source"),
    )
).resolve()
AUDIO_ORIGIN = Path(
    os.getenv(
        "SNAKE_REYERS_AUDIO_ORIGIN",
        str(ROOT.parent / "source-assets-unavailable"),
    )
).resolve()
AUDIO_PACK_TARGET_BYTES = 1_500_000_000
AUDIO_CORE_DIRS = (
    Path("voice"),
    Path("music/background"),
    Path("singing"),
    Path("songs"),
)
SKIP_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "private",
    "runs",
    "runtime",
    "updates",
}
SKIP_SUFFIXES = {".log", ".pyc", ".tmp"}


def _version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _include(path: Path, platform_name: str) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in SKIP_PARTS for part in relative.parts):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    if relative.as_posix() == "server/assets/audio-manifest.json":
        return False
    if relative.parts[:2] == ("game", "windows"):
        return platform_name == "windows"
    if relative.parts[:2] == ("game", "linux"):
        return platform_name == "linux"
    return True


def _files(platform_name: str) -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file() and _include(path, platform_name)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (
        json.dumps(
            manifest,
            ensure_ascii=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _windows_archive(
    version: str,
    audio_manifest: dict[str, object],
) -> Path:
    destination = OUTPUT_DIR / f"SnakeReyers-{version}-Windows-x64.zip"
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for source in _files("windows"):
            relative = source.relative_to(ROOT)
            archive.write(source, f"{ARCHIVE_ROOT}/{relative.as_posix()}")
        archive.writestr(
            f"{ARCHIVE_ROOT}/server/assets/audio-manifest.json",
            _manifest_bytes(audio_manifest),
        )
    return destination


def _linux_archive(
    version: str,
    audio_manifest: dict[str, object],
) -> Path:
    destination = OUTPUT_DIR / f"SnakeReyers-{version}-Linux-x64.tar.gz"
    with tarfile.open(destination, "w:gz", compresslevel=6) as archive:
        for source in _files("linux"):
            relative = source.relative_to(ROOT)
            archive.add(
                source,
                arcname=f"{ARCHIVE_ROOT}/{relative.as_posix()}",
                recursive=False,
            )
        payload = _manifest_bytes(audio_manifest)
        info = tarfile.TarInfo(
            f"{ARCHIVE_ROOT}/server/assets/audio-manifest.json"
        )
        info.size = len(payload)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(payload))
    return destination


def _asset_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []

    return sorted(
        path
        for path in base.rglob("*")
        if (
            path.is_file()
            and not any(part.startswith(".") for part in path.relative_to(AUDIO_SOURCE).parts)
            and path.suffix.lower() not in SKIP_SUFFIXES
        )
    )


def _sync_audio_source() -> None:
    if not AUDIO_ORIGIN.is_dir():
        return

    AUDIO_SOURCE.mkdir(parents=True, exist_ok=True)
    for source in sorted(
        path
        for path in AUDIO_ORIGIN.rglob("*")
        if (
            path.is_file()
            and not any(
                part.startswith(".")
                for part in path.relative_to(AUDIO_ORIGIN).parts
            )
            and path.suffix.lower() not in SKIP_SUFFIXES
        )
    ):
        relative = source.relative_to(AUDIO_ORIGIN)
        destination = AUDIO_SOURCE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.is_file():
            source_stat = source.stat()
            destination_stat = destination.stat()
            if (
                source_stat.st_ino == destination_stat.st_ino
                and source_stat.st_dev == destination_stat.st_dev
            ):
                continue
            if (
                source_stat.st_size == destination_stat.st_size
                and source_stat.st_mtime_ns == destination_stat.st_mtime_ns
            ):
                continue

        temporary = destination.with_name(
            f".{destination.name}.sync"
        )
        try:
            if temporary.exists():
                temporary.unlink()
            try:
                os.link(source, temporary)
            except OSError:
                shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()


def _audio_groups() -> list[list[Path]]:
    _sync_audio_source()
    if not AUDIO_SOURCE.is_dir():
        raise FileNotFoundError(
            f"Diretorio de audio ausente: {AUDIO_SOURCE}"
        )

    core: list[Path] = []
    for relative in AUDIO_CORE_DIRS:
        core.extend(_asset_files(AUDIO_SOURCE / relative))

    processed_root = AUDIO_SOURCE / "music" / "background_processed"
    groups: list[list[Path]] = [sorted(set(core))]
    current: list[Path] = []
    current_size = 0

    for song_dir in sorted(
        (path for path in processed_root.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    ):
        files = _asset_files(song_dir)
        size = sum(path.stat().st_size for path in files)
        if current and current_size + size > AUDIO_PACK_TARGET_BYTES:
            groups.append(current)
            current = []
            current_size = 0
        current.extend(files)
        current_size += size

    if current:
        groups.append(current)

    return [group for group in groups if group]


def _audio_archives(
    version: str,
) -> tuple[list[Path], dict[str, object]]:
    release_base = os.getenv(
        "SNAKE_REYERS_RELEASE_BASE_URL",
        (
            "https://github.com/golgol2/"
            "Snake-Reyers/"
            f"releases/download/v{version}"
        ),
    ).rstrip("/")
    archives: list[Path] = []

    for index, files in enumerate(_audio_groups(), start=1):
        name = f"SnakeReyers-{version}-Audio-{index:02d}.zip"
        destination = OUTPUT_DIR / name
        print(
            f"Montando {name} com {len(files)} arquivos...",
            flush=True,
        )
        with zipfile.ZipFile(
            destination,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            for source in files:
                relative = source.relative_to(AUDIO_SOURCE)
                archive.write(
                    source,
                    f"server/assets/{relative.as_posix()}",
                )
        archives.append(destination)

    packs = [
        {
            "name": archive.name,
            "bytes": archive.stat().st_size,
            "sha256": _sha256(archive),
            "url": f"{release_base}/{archive.name}",
        }
        for archive in archives
    ]
    return archives, {
        "version": version,
        "packs": packs,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    version = _version()
    audio_archives, audio_manifest = _audio_archives(version)
    archives = [
        _windows_archive(version, audio_manifest),
        _linux_archive(version, audio_manifest),
        *audio_archives,
    ]
    result = {
        "version": version,
        "packages": [
            {
                "name": archive.name,
                "bytes": archive.stat().st_size,
                "sha256": _sha256(archive),
            }
            for archive in archives
        ],
        "audio": audio_manifest,
    }
    manifest_path = OUTPUT_DIR / f"SnakeReyers-{version}-checksums.json"
    manifest_path.write_text(
        json.dumps(result, ensure_ascii=True, indent=2) + os.linesep,
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
