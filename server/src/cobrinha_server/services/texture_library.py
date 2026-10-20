from __future__ import annotations

import io
import re
import time
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from cobrinha_server.core.json_store import (
    read_json,
    write_json_atomic,
)
from cobrinha_server.core.settings import (
    TEXTURE_LIBRARY_DIR,
    TEXTURE_MANIFEST_FILE,
)


TEXTURE_TYPES: dict[str, str] = {
    "piso": "piso",
    "parede": "parede",
    "grama": "grama",
    "elevacao": "elevacao",
}

SUPPORTED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}

MAX_UPLOAD_BYTES = 24 * 1024 * 1024


def _slugify(value: str) -> str:
    normalized = (
        value.strip()
        .lower()
        .replace("ç", "c")
        .replace("ã", "a")
        .replace("á", "a")
        .replace("à", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
    )
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = normalized.strip("_")
    return normalized or "textura"


def _normalize_type(texture_type: str) -> str:
    key = str(texture_type or "").strip().lower()
    if key not in TEXTURE_TYPES:
        raise ValueError(
            "Tipo invalido. Use piso, parede, grama ou elevacao."
        )
    return TEXTURE_TYPES[key]


def _empty_manifest() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": 0.0,
        "textures": [],
    }


def load_manifest() -> dict[str, Any]:
    manifest = read_json(
        TEXTURE_MANIFEST_FILE,
        _empty_manifest(),
    )

    if not isinstance(manifest, dict):
        manifest = _empty_manifest()

    textures = manifest.get("textures")
    if not isinstance(textures, list):
        textures = []

    normalized: list[dict[str, Any]] = []
    for item in textures:
        if not isinstance(item, dict):
            continue

        texture_type = str(item.get("type") or "").strip()
        path = str(item.get("path") or "").strip()
        if texture_type not in TEXTURE_TYPES or not path:
            continue

        normalized.append(
            {
                "id": str(item.get("id") or uuid.uuid4().hex),
                "type": texture_type,
                "label": str(item.get("label") or item.get("id") or ""),
                "path": path,
                "enabled": bool(item.get("enabled", True)),
                "width": int(item.get("width") or 0),
                "height": int(item.get("height") or 0),
                "source_filename": str(item.get("source_filename") or ""),
                "created_at": float(item.get("created_at") or 0.0),
            }
        )

    return {
        "version": int(manifest.get("version") or 1),
        "updated_at": float(manifest.get("updated_at") or 0.0),
        "textures": normalized,
    }


def save_manifest(manifest: dict[str, Any]) -> None:
    manifest["version"] = 1
    manifest["updated_at"] = time.time()
    write_json_atomic(
        TEXTURE_MANIFEST_FILE,
        manifest,
    )


def status() -> dict[str, Any]:
    manifest = load_manifest()
    by_type: dict[str, int] = {
        texture_type: 0
        for texture_type in TEXTURE_TYPES
    }

    for item in manifest["textures"]:
        if item.get("enabled", True):
            texture_type = str(item.get("type") or "")
            by_type[texture_type] = by_type.get(texture_type, 0) + 1

    return {
        "manifest_path": str(TEXTURE_MANIFEST_FILE),
        "library_dir": str(TEXTURE_LIBRARY_DIR),
        "types": list(TEXTURE_TYPES),
        "counts": by_type,
        "manifest": manifest,
    }


def import_texture(
    *,
    texture_type: str,
    label: str,
    source_filename: str,
    data: bytes,
) -> dict[str, Any]:
    if len(data) <= 0:
        raise ValueError("Arquivo vazio.")

    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Arquivo excede 24 MB.")

    normalized_type = _normalize_type(texture_type)
    extension = Path(source_filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Formato invalido. Use PNG, JPG, JPEG ou WEBP.")

    base_label = label.strip() or Path(source_filename).stem
    slug = _slugify(base_label)

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise ValueError(f"Imagem invalida: {exc}") from exc

    if image.width <= 0 or image.height <= 0:
        raise ValueError("Imagem sem dimensoes validas.")

    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA")

    texture_id = (
        f"{normalized_type}_{slug}_{uuid.uuid4().hex[:8]}"
    )
    texture_dir = TEXTURE_LIBRARY_DIR / normalized_type
    texture_dir.mkdir(parents=True, exist_ok=True)

    output_path = texture_dir / f"{texture_id}.png"
    image.save(output_path, format="PNG", optimize=True)

    entry = {
        "id": texture_id,
        "type": normalized_type,
        "label": base_label,
        "path": str(output_path),
        "enabled": True,
        "width": int(image.width),
        "height": int(image.height),
        "source_filename": source_filename,
        "created_at": time.time(),
    }

    manifest = load_manifest()
    manifest["textures"].append(entry)
    save_manifest(manifest)

    return {
        "entry": entry,
        "manifest": load_manifest(),
    }
