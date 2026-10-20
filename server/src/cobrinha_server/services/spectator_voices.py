from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cobrinha_server.services.tts_service import (
    available_voice_paths,
)


def _metadata_user_key(
    metadata: dict[str, Any],
) -> str:
    for key in (
        "user_id",
        "username",
        "display_name",
        "avatar_url",
        "avatar_path",
    ):
        value = str(
            metadata.get(key)
            or ""
        ).strip()

        if value:
            return value

    return "spectator"


def is_spectator_speaker(
    metadata: dict[str, Any],
) -> bool:
    return (
        str(
            metadata.get("speaker")
            or ""
        )
        .strip()
        .casefold()
        == "spectator"
    )


def voice_path_for_metadata(
    metadata: dict[str, Any],
) -> Path | None:
    if not is_spectator_speaker(metadata):
        return None

    voices = available_voice_paths()
    if not voices:
        return None

    digest = hashlib.sha256(
        _metadata_user_key(metadata).encode(
            "utf-8",
            errors="ignore",
        )
    ).digest()
    index = int.from_bytes(
        digest[:4],
        "big",
    ) % len(voices)

    return voices[index]
