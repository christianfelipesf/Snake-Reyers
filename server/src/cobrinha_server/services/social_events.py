from __future__ import annotations

from typing import Any


def _clean(value: object, limit: int = 240) -> str:
    text = " ".join(
        str(value or "").strip().split()
    )

    if len(text) <= limit:
        return text

    return text[:limit].rstrip()


def normalize_social_user(
    payload: dict[str, Any] | None,
) -> dict[str, str]:
    raw = (
        payload
        if isinstance(payload, dict)
        else {}
    )

    username = _clean(
        raw.get("username")
        or raw.get("unique_id")
        or raw.get("uniqueId")
        or "",
        96,
    )

    user_id = _clean(
        raw.get("user_id")
        or raw.get("id")
        or username,
        128,
    )

    display_name = _clean(
        raw.get("display_name")
        or raw.get("nickname")
        or raw.get("name")
        or username
        or "visitante",
        120,
    )

    avatar_url = _clean(
        raw.get("avatar_url")
        or raw.get("profile_image")
        or raw.get("profile_photo")
        or raw.get("profilePictureUrl")
        or "",
        1200,
    )

    comment = _clean(
        raw.get("comment")
        or raw.get("text")
        or "",
        500,
    )

    return {
        "user_id": user_id,
        "username": username,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "comment": comment,
    }


def spectator_user_message(
    payload: dict[str, Any] | None,
    *,
    avatar_path: str = "",
    source: str = "social",
) -> dict[str, Any]:
    user = normalize_social_user(payload)

    return {
        "type": "spectator_user_selected",
        "source": source,
        "payload": {
            **user,
            "avatar_path": str(
                avatar_path or ""
            ).strip(),
            "metadata": {
                "source": source,
            },
        },
    }
