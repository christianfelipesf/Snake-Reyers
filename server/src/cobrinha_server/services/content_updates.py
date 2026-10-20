from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

from cobrinha_server.core.json_store import read_json, write_json_atomic
from cobrinha_server.core.settings import ASSETS_DIR, PRIVATE_DIR, PROJECT_DIR


DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/golgol2/"
    "Snake-Reyers/main/content-manifest.json"
)
CONFIG_FILE = PRIVATE_DIR / "content-updates.json"
STATE_FILE = PRIVATE_DIR / "content-update-state.json"
WORK_DIR = PROJECT_DIR / "runtime" / "content-updates"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
CHECK_INTERVAL_SECONDS = max(
    300,
    int(os.getenv("SNAKE_REYERS_CONTENT_CHECK_SECONDS", "21600")),
)
BLOCKED_RETRY_SECONDS = 60
SUPPORTED_TYPES = {
    "background_music": "music/background",
    "gift_reaction": "content/reactions",
}
SUPPORTED_REACTION_ACTIONS = {
    "gift_cannon",
    "heart_me_band",
}


class ContentUpdateError(RuntimeError):
    pass


class ContentUpdateBusy(ContentUpdateError):
    pass


class ContentUpdateBlocked(ContentUpdateError):
    pass


_STATUS_LOCK = threading.RLock()
_JOB_LOCK = threading.Lock()
_BACKGROUND_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()
_STATUS: dict[str, Any] = {
    "busy": False,
    "phase": "idle",
    "message": "Atualizacoes de conteudo ainda nao verificadas.",
    "checked_at": 0.0,
    "installed_at": 0.0,
    "available": [],
    "available_count": 0,
    "download_bytes": 0,
    "last_error": "",
}


def _configuration() -> dict[str, Any]:
    raw = read_json(CONFIG_FILE, {})
    if not isinstance(raw, dict):
        raw = {}
    return {
        "auto_install": bool(raw.get("auto_install", True)),
        "manifest_url": str(
            raw.get("manifest_url")
            or os.getenv("SNAKE_REYERS_CONTENT_MANIFEST_URL", "")
            or DEFAULT_MANIFEST_URL
        ).strip(),
    }


def update_configuration(*, auto_install: object) -> dict[str, Any]:
    config = _configuration()
    config["auto_install"] = bool(auto_install)
    write_json_atomic(CONFIG_FILE, config)
    return config


def _state() -> dict[str, Any]:
    raw = read_json(STATE_FILE, {})
    if not isinstance(raw, dict):
        raw = {}
    installed = raw.get("installed")
    if not isinstance(installed, dict):
        installed = {}
    return {
        "schema_version": 1,
        "catalog_revision": int(raw.get("catalog_revision") or 0),
        "installed": installed,
        "updated_at": float(raw.get("updated_at") or 0.0),
    }


def _set_status(**values: Any) -> None:
    with _STATUS_LOCK:
        _STATUS.update(values)


def public_status() -> dict[str, Any]:
    with _STATUS_LOCK:
        status = dict(_STATUS)
        status["available"] = [
            dict(item)
            for item in _STATUS.get("available", [])
            if isinstance(item, dict)
        ]
    state = _state()
    return {
        "ok": not bool(status.get("last_error")),
        **status,
        "configuration": _configuration(),
        "catalog_revision": state["catalog_revision"],
        "installed_count": len(state["installed"]),
        "live_active": _live_active(),
    }


def _live_active() -> bool:
    try:
        from cobrinha_server.services import game_launcher

        state = game_launcher.status()
        active_states = {"starting", "running", "stopping"}
        return (
            bool(state.get("running"))
            or str(state.get("state") or "").lower()
            in active_states
        )
    except Exception:
        return False


def _open_url(url: str, timeout: float = 30.0):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"https", "file"}:
        raise ContentUpdateError("O catalogo exige uma URL HTTPS.")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Snake-Reyers-Content-Updater/1.0"},
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _load_manifest(url: str) -> dict[str, Any]:
    with _open_url(url) as response:
        payload = response.read(MAX_MANIFEST_BYTES + 1)
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ContentUpdateError("O catalogo de conteudo excede o limite permitido.")
    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContentUpdateError("Catalogo de conteudo invalido.") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("items", []), list):
        raise ContentUpdateError("Catalogo de conteudo invalido.")
    return manifest


def _version_tuple(value: object) -> tuple[int, ...]:
    parts: list[int] = []
    for item in str(value or "0").strip().lstrip("vV").split("."):
        digits = "".join(character for character in item if character.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts or [0])


def _safe_relative(value: object) -> Path:
    text = str(value or "").strip().replace("\\", "/").strip("/")
    relative = Path(text)
    if not text or relative.is_absolute() or ".." in relative.parts:
        raise ContentUpdateError("Destino inseguro no catalogo de conteudo.")
    return relative


def _normalized_item(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContentUpdateError("Item invalido no catalogo de conteudo.")
    item_id = str(raw.get("id") or "").strip()
    content_type = str(raw.get("type") or "").strip()
    version = str(raw.get("version") or "").strip()
    url = str(raw.get("url") or "").strip()
    digest = str(raw.get("sha256") or "").strip().lower()
    target = _safe_relative(raw.get("target"))
    if not item_id or not version:
        raise ContentUpdateError("Item sem id ou versao no catalogo.")
    if content_type not in SUPPORTED_TYPES:
        raise ContentUpdateError(f"Tipo de conteudo nao suportado: {content_type}")
    allowed_root = Path(SUPPORTED_TYPES[content_type])
    if allowed_root not in target.parents:
        raise ContentUpdateError(f"Destino nao permitido para {item_id}.")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"https", "file"} or len(digest) != 64:
        raise ContentUpdateError(f"Pacote invalido para {item_id}.")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ContentUpdateError(f"SHA-256 invalido para {item_id}.") from exc
    gift_names = raw.get("gift_names", [])
    if isinstance(gift_names, str):
        gift_names = [gift_names]
    if not isinstance(gift_names, list):
        gift_names = []
    item = {
        "id": item_id,
        "title": str(raw.get("title") or item_id).strip(),
        "type": content_type,
        "version": version,
        "url": url,
        "sha256": digest,
        "bytes": max(0, int(raw.get("bytes") or 0)),
        "target": target.as_posix(),
        "gift_names": [str(name).strip() for name in gift_names if str(name).strip()],
        "action": str(raw.get("action") or "").strip(),
    }
    if content_type == "gift_reaction" and (
        not item["gift_names"]
        or item["action"] not in SUPPORTED_REACTION_ACTIONS
    ):
        raise ContentUpdateError(f"Reacao {item_id} sem presente ou acao suportada.")
    return item


def _gift_key(value: object) -> str:
    normalized = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def reaction_for_gift_name(gift_name: object) -> dict[str, Any] | None:
    requested = _gift_key(gift_name)
    if not requested:
        return None
    for item_id, item in _state()["installed"].items():
        if not isinstance(item, dict) or item.get("type") != "gift_reaction":
            continue
        names = item.get("gift_names", [])
        if not isinstance(names, list):
            continue
        if requested in {_gift_key(name) for name in names}:
            return {
                "id": item_id,
                "action": str(item.get("action") or ""),
                "target": str(item.get("target") or ""),
            }
    return None


def _available_items(manifest: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    installed = state["installed"]
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in manifest.get("items", []):
        item = _normalized_item(raw)
        if item["id"] in seen:
            raise ContentUpdateError(f"Item duplicado no catalogo: {item['id']}")
        seen.add(item["id"])
        current = installed.get(item["id"], {})
        current_version = current.get("version", "0") if isinstance(current, dict) else "0"
        if _version_tuple(item["version"]) > _version_tuple(current_version):
            result.append(item)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(item: dict[str, Any], destination: Path) -> None:
    _set_status(phase="downloading", message=f"Baixando {item['title']}...")
    with _open_url(item["url"], timeout=180.0) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    if _sha256(destination) != item["sha256"]:
        raise ContentUpdateError(f"SHA-256 nao confere para {item['title']}.")


def _extract_zip(archive: Path, destination: Path) -> None:
    if not zipfile.is_zipfile(archive):
        raise ContentUpdateError("O pacote de conteudo precisa ser um arquivo ZIP.")
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            member_path = Path(member.filename.replace("\\", "/"))
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ContentUpdateError("Caminho inseguro dentro do pacote.")
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ContentUpdateError("Links simbolicos nao sao aceitos.")
        bundle.extractall(destination)


def _install_item(item: dict[str, Any]) -> None:
    if _live_active():
        raise ContentUpdateBlocked("O jogo foi aberto. O conteudo sera instalado depois que ele fechar.")
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="content-", dir=WORK_DIR) as temporary_name:
        temporary = Path(temporary_name)
        archive = temporary / "package.zip"
        incoming = temporary / "incoming"
        _download(item, archive)
        _set_status(phase="installing", message=f"Instalando {item['title']}...")
        _extract_zip(archive, incoming)
        target = (ASSETS_DIR / item["target"]).resolve()
        assets_root = ASSETS_DIR.resolve()
        if target == assets_root or assets_root not in target.parents:
            raise ContentUpdateError("Destino do conteudo saiu da pasta de assets.")
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = temporary / "backup"
        had_target = target.exists()
        try:
            if had_target:
                os.replace(target, backup)
            os.replace(incoming, target)
        except Exception:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            if backup.exists():
                os.replace(backup, target)
            raise


def synchronize(*, install: bool) -> dict[str, Any]:
    if not _JOB_LOCK.acquire(blocking=False):
        raise ContentUpdateBusy("Outra verificacao de conteudo ja esta em andamento.")
    try:
        _set_status(
            busy=True,
            phase="checking",
            message="Consultando novidades no GitHub...",
            last_error="",
        )
        config = _configuration()
        manifest = _load_manifest(config["manifest_url"])
        state = _state()
        available = _available_items(manifest, state)
        public_items = [
            {
                key: item[key]
                for key in ("id", "title", "type", "version", "bytes")
            }
            for item in available
        ]
        _set_status(
            checked_at=time.time(),
            available=public_items,
            available_count=len(available),
            download_bytes=sum(item["bytes"] for item in available),
            phase="available" if available else "current",
            message=(
                f"{len(available)} novidade(s) encontrada(s)."
                if available
                else "O conteudo esta atualizado."
            ),
        )
        if not install or not available:
            state["catalog_revision"] = int(manifest.get("revision") or 0)
            state["updated_at"] = time.time()
            write_json_atomic(STATE_FILE, state)
            _set_status(busy=False)
            return public_status()
        if _live_active():
            raise ContentUpdateBlocked("Feche o jogo antes de instalar novos conteudos.")

        installed_now: list[str] = []
        for item in available:
            _install_item(item)
            state["installed"][item["id"]] = {
                "version": item["version"],
                "sha256": item["sha256"],
                "type": item["type"],
                "target": item["target"],
                "gift_names": item["gift_names"],
                "action": item["action"],
                "installed_at": time.time(),
            }
            state["catalog_revision"] = int(manifest.get("revision") or 0)
            state["updated_at"] = time.time()
            write_json_atomic(STATE_FILE, state)
            installed_now.append(item["id"])

        _set_status(
            busy=False,
            installed_at=time.time(),
            available=[],
            available_count=0,
            download_bytes=0,
            phase="installed",
            message=f"{len(installed_now)} conteudo(s) instalado(s). Disponiveis na proxima abertura do jogo.",
        )
        result = public_status()
        result["installed_now"] = installed_now
        return result
    except Exception as exc:
        _set_status(
            phase="blocked" if isinstance(exc, ContentUpdateBlocked) else "error",
            message=str(exc),
            last_error=str(exc),
        )
        raise
    finally:
        _set_status(busy=False)
        _JOB_LOCK.release()


def _background_sync() -> None:
    retry_after = 0
    while not _STOP_EVENT.is_set():
        try:
            synchronize(install=_configuration()["auto_install"])
            retry_after = CHECK_INTERVAL_SECONDS
        except ContentUpdateBlocked:
            retry_after = BLOCKED_RETRY_SECONDS
        except ContentUpdateBusy:
            retry_after = BLOCKED_RETRY_SECONDS
        except Exception:
            retry_after = min(CHECK_INTERVAL_SECONDS, 15 * 60)
        _STOP_EVENT.wait(retry_after)


def start_startup_sync() -> None:
    global _BACKGROUND_THREAD
    if _BACKGROUND_THREAD and _BACKGROUND_THREAD.is_alive():
        return
    _STOP_EVENT.clear()
    _BACKGROUND_THREAD = threading.Thread(
        target=_background_sync,
        name="content-update-background",
        daemon=True,
    )
    _BACKGROUND_THREAD.start()


def stop_background_sync() -> None:
    _STOP_EVENT.set()
