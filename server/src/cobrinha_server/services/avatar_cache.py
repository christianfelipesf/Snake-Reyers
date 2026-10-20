from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from cobrinha_server.core.settings import RUNS_DIR


AVATAR_CACHE_DIR = (
    RUNS_DIR
    / "profile_avatars"
)

MAX_AVATAR_BYTES = 5 * 1024 * 1024


def _safe_suffix(
    content_type: str,
    source_url: str,
) -> str:
    lowered = str(
        content_type or ""
    ).casefold()

    if "png" in lowered:
        return ".png"

    if (
        "jpeg" in lowered
        or "jpg" in lowered
    ):
        return ".jpg"

    if "webp" in lowered:
        return ".webp"

    suffix = Path(
        urlsplit(source_url).path
    ).suffix.casefold()

    if suffix in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    }:
        return (
            ".jpg"
            if suffix == ".jpeg"
            else suffix
        )

    return ".img"


def cache_profile_avatar(
    avatar_url: str,
    *,
    user_key: str = "",
    timeout: float = 8.0,
) -> dict[str, Any]:
    url = str(
        avatar_url or ""
    ).strip()

    if not url:
        return {
            "ok": False,
            "cached": False,
            "path": "",
            "error": "avatar_url vazio",
        }

    parsed = urlsplit(url)

    if (
        parsed.scheme not in {
            "http",
            "https",
        }
        or not parsed.hostname
    ):
        return {
            "ok": False,
            "cached": False,
            "path": "",
            "error":
                "avatar_url precisa ser http/https",
        }

    host = parsed.hostname.casefold()

    if host in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        return {
            "ok": False,
            "cached": False,
            "path": "",
            "error":
                "host local nao permitido",
        }

    AVATAR_CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    digest = hashlib.sha256(
        (
            str(user_key or "")
            + "\n"
            + url
        ).encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:24]

    for existing in (
        AVATAR_CACHE_DIR
        .glob(f"{digest}.*")
    ):
        if (
            existing.is_file()
            and existing.stat().st_size > 0
        ):
            return {
                "ok": True,
                "cached": True,
                "path": str(
                    existing.resolve()
                ),
                "bytes":
                    existing.stat().st_size,
            }

    request = Request(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0 CobrinhaLive/1.0",
            "Accept":
                "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )

    try:
        with urlopen(
            request,
            timeout=max(
                1.0,
                float(timeout),
            ),
        ) as response:
            content_type = str(
                response.headers.get(
                    "Content-Type",
                    "",
                )
            )

            if (
                content_type
                and "image/" not in
                content_type.casefold()
            ):
                return {
                    "ok": False,
                    "cached": False,
                    "path": "",
                    "error":
                        "resposta nao e imagem",
                }

            data = response.read(
                MAX_AVATAR_BYTES + 1
            )

    except Exception as exc:
        return {
            "ok": False,
            "cached": False,
            "path": "",
            "error":
                f"{type(exc).__name__}: {exc}",
        }

    if not data:
        return {
            "ok": False,
            "cached": False,
            "path": "",
            "error": "imagem vazia",
        }

    if len(data) > MAX_AVATAR_BYTES:
        return {
            "ok": False,
            "cached": False,
            "path": "",
            "error":
                "imagem excede limite",
        }

    suffix = _safe_suffix(
        content_type,
        url,
    )

    destination = (
        AVATAR_CACHE_DIR
        / f"{digest}{suffix}"
    )

    temporary = destination.with_suffix(
        destination.suffix + ".tmp"
    )

    temporary.write_bytes(data)
    temporary.replace(destination)

    return {
        "ok": True,
        "cached": False,
        "path": str(
            destination.resolve()
        ),
        "bytes": len(data),
    }
