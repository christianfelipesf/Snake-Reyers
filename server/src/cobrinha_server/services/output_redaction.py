from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse


_URL_RE = re.compile(
    r"(?:rtmp|rtmps|https?)://[^\s\"']+",
    re.IGNORECASE,
)


def fingerprint(
    value: object,
) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    return hashlib.sha256(
        text.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:16]


def public_destination(
    value: object,
) -> dict[str, Any]:
    text = str(value or "").strip()

    if not text:
        return {
            "present": False,
            "scheme": "",
            "host": "",
            "app": "",
            "fingerprint": "",
        }

    parsed = urlparse(text)

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    return {
        "present": True,
        "scheme":
            str(parsed.scheme or ""),
        "host":
            str(parsed.hostname or ""),
        "app":
            str(
                parts[0]
                if parts
                else ""
            ),
        "fingerprint":
            fingerprint(text),
    }


def redacted_destination(
    value: object,
) -> str:
    info = public_destination(
        value
    )

    if not info["present"]:
        return ""

    return (
        f"{info['scheme']}://"
        f"{info['host']}/"
        f"{info['app']}/"
        f"<redacted fp={info['fingerprint']}>"
    )


def redact_text(
    value: object,
    *,
    destination: object = "",
) -> str:
    text = str(value or "")

    full = str(
        destination or ""
    ).strip()

    if full:
        text = text.replace(
            full,
            redacted_destination(
                full
            ),
        )

    return _URL_RE.sub(
        "[destination-redacted]",
        text,
    )
