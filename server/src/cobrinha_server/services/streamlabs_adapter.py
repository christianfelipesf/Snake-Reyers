from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from cobrinha_server.core.settings import (
    STREAMLABS_TIKTOK_CONFIG_FILE,
)
from cobrinha_server.services.output_credentials import (
    OutputCredential,
)
from cobrinha_server.services.output_redaction import (
    public_destination,
)


class StreamlabsAdapterError(
    RuntimeError
):
    pass


def load_config() -> dict[str, Any]:
    path = Path(
        STREAMLABS_TIKTOK_CONFIG_FILE
    )

    if not path.is_file():
        return {
            "configured": False,
            "token_present": False,
            "title": "",
            "game": "",
            "audience_type": "",
        }

    try:
        raw = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        raise StreamlabsAdapterError(
            f"config_invalid:{type(exc).__name__}"
        ) from exc

    if not isinstance(
        raw,
        dict,
    ):
        raise StreamlabsAdapterError(
            "config_not_object"
        )

    token = str(
        raw.get("token")
        or ""
    ).strip()

    return {
        "configured": bool(token),
        "token_present": bool(token),
        "title": str(
            raw.get("title")
            or ""
        ),
        "game": str(
            raw.get("game")
            or ""
        ),
        "audience_type": str(
            raw.get("audience_type")
            or ""
        ),
        "last_stream_id": str(
            raw.get("last_stream_id")
            or ""
        ),
        "last_rtmp_host": str(
            raw.get("last_rtmp_host")
            or ""
        ),
        "last_rtmp_app": str(
            raw.get("last_rtmp_app")
            or ""
        ),
        "last_rtmp_fingerprint": str(
            raw.get("last_rtmp_fingerprint")
            or ""
        ),
        "previous_rtmp_fingerprint": str(
            raw.get("previous_rtmp_fingerprint")
            or ""
        ),
    }


def public_status() -> dict[str, Any]:
    config = load_config()

    return {
        "configured":
            bool(config.get("configured")),
        "token_present":
            bool(config.get("token_present")),
        "title":
            str(config.get("title") or ""),
        "game":
            str(config.get("game") or ""),
        "audience_type":
            str(
                config.get("audience_type")
                or ""
            ),
        "last_stream_id":
            str(
                config.get("last_stream_id")
                or ""
            ),
        "last_rtmp_host":
            str(
                config.get("last_rtmp_host")
                or ""
            ),
        "last_rtmp_app":
            str(
                config.get("last_rtmp_app")
                or ""
            ),
        "last_rtmp_fingerprint":
            str(
                config.get(
                    "last_rtmp_fingerprint"
                )
                or ""
            ),
        "previous_rtmp_fingerprint":
            str(
                config.get(
                    "previous_rtmp_fingerprint"
                )
                or ""
            ),
        "external_call_enabled":
            False,
    }


def credential_from_response(
    payload: object,
) -> OutputCredential:
    if not isinstance(
        payload,
        dict,
    ):
        raise StreamlabsAdapterError(
            "response_not_object"
        )

    base = str(
        payload.get("rtmp")
        or payload.get("rtmp_url")
        or ""
    ).strip().rstrip("/")

    key = str(
        payload.get("key")
        or payload.get("stream_key")
        or ""
    ).strip().lstrip("/")

    if not base or not key:
        raise StreamlabsAdapterError(
            "missing_rtmp_or_key"
        )

    return OutputCredential(
        destination_url=(
            base
            + "/"
            + key
        ),
        provider="streamlabs",
        session_id=str(
            payload.get("stream_id")
            or ""
        ),
        title=str(
            payload.get("title")
            or ""
        ),
        category=str(
            payload.get("game")
            or payload.get("category")
            or ""
        ),
    )


def acquire_credential(
    *,
    title: str = "",
    game: str = "",
    audience_type: str = "",
    transport: Callable[
        [dict[str, Any]],
        dict[str, Any],
    ]
    | None = None,
) -> OutputCredential:
    config = load_config()

    if not config.get("configured"):
        raise StreamlabsAdapterError(
            "streamlabs_not_configured"
        )

    if transport is None:
        raise StreamlabsAdapterError(
            "external_transport_disabled"
        )

    request = {
        "title":
            str(
                title
                or config.get("title")
                or ""
            ),
        "game":
            str(
                game
                or config.get("game")
                or ""
            ),
        "audience_type":
            str(
                audience_type
                or config.get(
                    "audience_type"
                )
                or ""
            ),
        # O token fica exclusivamente dentro do adaptador
        # e nunca aparece no retorno publico.
        "_token_required": True,
    }

    result = transport(
        request
    )

    credential = (
        credential_from_response(
            result
        )
    )

    public = credential.public_info()

    if (
        not public["destination"]["present"]
        or not public["destination"]["host"]
    ):
        raise StreamlabsAdapterError(
            "invalid_destination"
        )

    return credential


def credential_public_info(
    credential: OutputCredential,
) -> dict[str, Any]:
    return {
        **credential.public_info(),
        "destination":
            public_destination(
                credential.destination_url
            ),
    }
