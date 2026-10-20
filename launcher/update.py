#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT_DIR / "VERSION"
PRIVATE_CONFIG_FILE = ROOT_DIR / "server" / "private" / "update.json"
UPDATES_DIR = ROOT_DIR / "updates"
DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/golgol2/"
    "Snake-Reyers/main/update-manifest.json"
)
PROTECTED_PREFIXES = (
    ".git",
    "updates",
    "server/private",
    "server/runs",
    "server/assets",
    "server/runtime",
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _version_tuple(value: object) -> tuple[int, ...]:
    parts: list[int] = []
    for item in str(value or "0").strip().lstrip("vV").split("."):
        digits = "".join(character for character in item if character.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts or [0])


def _platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    architecture = "x86_64" if machine in {"amd64", "x86_64"} else machine
    if system == "windows":
        return f"windows-{architecture}"
    if system == "linux":
        return f"linux-{architecture}"
    raise RuntimeError(f"Plataforma nao suportada: {system}-{architecture}")


def _manifest_url(explicit: str = "") -> str:
    if explicit.strip():
        return explicit.strip()
    environment = os.getenv("SNAKE_REYERS_UPDATE_MANIFEST_URL", "").strip()
    if environment:
        return environment
    return str(
        _read_json(PRIVATE_CONFIG_FILE).get("manifest_url")
        or DEFAULT_MANIFEST_URL
    ).strip()


def _open_url(url: str, timeout: float = 20.0):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"https", "file"}:
        raise ValueError("A atualizacao exige uma URL HTTPS.")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Snake-Reyers-Updater/0.1"},
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _load_manifest(url: str) -> dict[str, Any]:
    with _open_url(url) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Manifesto de atualizacao invalido.")
    return payload


def _package_for(manifest: dict[str, Any]) -> dict[str, str]:
    packages = manifest.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("Manifesto sem pacotes.")
    package = packages.get(_platform_key())
    if not isinstance(package, dict):
        raise ValueError(f"Pacote ausente para {_platform_key()}.")
    url = str(package.get("url") or "").strip()
    digest = str(package.get("sha256") or "").strip().lower()
    if not url or len(digest) != 64:
        raise ValueError("URL ou SHA-256 do pacote invalido.")
    return {"url": url, "sha256": digest}


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _open_url(url, timeout=120.0) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_target(root: Path, member_name: str) -> Path:
    target = (root / member_name).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"Caminho inseguro no pacote: {member_name}")
    return target


def _extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                _safe_target(destination, member.filename)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError("Links simbolicos nao sao aceitos na atualizacao.")
            bundle.extractall(destination)
        return
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                _safe_target(destination, member.name)
                if member.issym() or member.islnk():
                    raise ValueError("Links simbolicos nao sao aceitos na atualizacao.")
            bundle.extractall(destination, filter="data")
        return
    raise ValueError("Formato de pacote nao suportado.")


def _payload_root(staging: Path) -> Path:
    if (staging / "VERSION").is_file():
        return staging
    children = [path for path in staging.iterdir() if path.is_dir()]
    if len(children) == 1 and (children[0] / "VERSION").is_file():
        return children[0]
    raise ValueError("Pacote sem VERSION na raiz.")


def _is_protected(relative: Path) -> bool:
    normalized = relative.as_posix().strip("/")
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in PROTECTED_PREFIXES
    )


def _install_payload(payload_root: Path) -> int:
    copied = 0
    for source in payload_root.rglob("*"):
        relative = source.relative_to(payload_root)
        if _is_protected(relative) or source.is_symlink():
            continue
        target = ROOT_DIR / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".update")
        shutil.copy2(source, temporary)
        temporary.replace(target)
        copied += 1
    linux_game = ROOT_DIR / "game" / "linux" / "SnakeReyers.x86_64"
    if linux_game.is_file():
        linux_game.chmod(linux_game.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    return copied


def _run_post_install() -> str:
    system = platform.system().lower()
    if system == "windows":
        script = ROOT_DIR / "launcher" / "create_shortcut.ps1"
        if not script.is_file():
            return ""
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-InstallRoot",
            str(ROOT_DIR),
        ]
    elif system == "linux":
        script = ROOT_DIR / "launcher" / "create_shortcut_linux.sh"
        if not script.is_file():
            return ""
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        command = ["bash", str(script)]
    else:
        return ""

    completed = subprocess.run(
        command,
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            detail or "Nao foi possivel criar o atalho de inicializacao."
        )
    return completed.stdout.strip()


def check_and_update(manifest_url: str, install: bool) -> dict[str, Any]:
    manifest = _load_manifest(manifest_url)
    current = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.is_file() else "0.0.0"
    available = str(manifest.get("version") or "0.0.0").strip()
    result: dict[str, Any] = {
        "current": current,
        "available": available,
        "update_available": _version_tuple(available) > _version_tuple(current),
        "installed": False,
    }
    if not result["update_available"] or not install:
        return result

    package = _package_for(manifest)
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(urllib.parse.urlparse(package["url"]).path).suffix or ".package"
    with tempfile.TemporaryDirectory(prefix="snake-reyers-", dir=UPDATES_DIR) as temporary_dir:
        temporary = Path(temporary_dir)
        archive = temporary / f"download{suffix}"
        staging = temporary / "staging"
        _download(package["url"], archive)
        actual_digest = _sha256(archive)
        if actual_digest != package["sha256"]:
            raise ValueError("SHA-256 do pacote nao confere.")
        _extract_archive(archive, staging)
        payload = _payload_root(staging)
        packaged_version = (payload / "VERSION").read_text(encoding="utf-8").strip()
        if packaged_version != available:
            raise ValueError("A versao do pacote difere do manifesto.")
        result["files_updated"] = _install_payload(payload)
        result["installed"] = True
        try:
            result["post_install"] = _run_post_install()
        except Exception as exc:
            result["post_install_warning"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Atualizador do Snake Reyers Lite")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--install", action="store_true")
    arguments = parser.parse_args()
    url = _manifest_url(arguments.manifest)
    if not url:
        print("Atualizacao automatica ainda nao configurada.")
        return 0
    try:
        result = check_and_update(url, arguments.install)
    except Exception as exc:
        print(f"Falha ao verificar atualizacao: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
