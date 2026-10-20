from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import (
    Any,
    Callable,
)
from urllib.parse import (
    quote,
    urlsplit,
)

from cobrinha_server.core.settings import (
    STREAMLABS_TIKTOK_CONFIG_FILE,
)
from cobrinha_server.services.output_credentials import (
    OutputCredential,
)
from cobrinha_server.services.output_redaction import (
    fingerprint,
    public_destination,
)


NETWORK_GATE_ENV = (
    "COBRINHA_ALLOW_STREAMLABS_NETWORK"
)

STREAMLABS_API_BASE = (
    "https://streamlabs.com/api/v5/slobs/tiktok"
)


class StreamlabsProviderError(
    RuntimeError
):
    pass


Transport = Callable[
    [
        str,
        str,
        dict[str, str],
        dict[str, Any] | None,
    ],
    dict[str, Any],
]


def network_enabled() -> bool:
    return (
        str(
            os.environ.get(
                NETWORK_GATE_ENV,
                ""
            )
        ).strip()
        == "1"
    )


def _load_private() -> dict[str, Any]:
    path = Path(
        STREAMLABS_TIKTOK_CONFIG_FILE
    )

    if not path.is_file():
        raise StreamlabsProviderError(
            "streamlabs_config_missing"
        )

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        raise StreamlabsProviderError(
            f"streamlabs_config_invalid:{type(exc).__name__}"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise StreamlabsProviderError(
            "streamlabs_config_not_object"
        )

    return payload


def _save_private(
    update: dict[str, Any],
) -> dict[str, Any]:
    path = Path(
        STREAMLABS_TIKTOK_CONFIG_FILE
    )

    try:
        payload = _load_private()
    except StreamlabsProviderError:
        payload = {}

    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    for key, value in update.items():
        payload[str(key)] = str(
            value or ""
        ).strip()

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return payload


def _destination_details(
    destination_url: object,
) -> dict[str, str]:
    text = str(
        destination_url
        or ""
    ).strip()

    if not text:
        return {
            "fingerprint": "",
            "host": "",
            "app": "",
        }

    try:
        parsed = urlsplit(
            text
        )
    except ValueError:
        return {
            "fingerprint":
                fingerprint(text),
            "host": "",
            "app": "",
        }

    path_parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    return {
        "fingerprint":
            fingerprint(text),
        "host":
            parsed.netloc
            or parsed.hostname
            or "",
        "app":
            path_parts[0]
            if path_parts
            else "",
    }


def public_config_status() -> dict[str, Any]:
    payload = _load_private()

    return {
        "configured":
            bool(
                str(
                    payload.get("token")
                    or ""
                ).strip()
            ),
        "token_present":
            bool(
                str(
                    payload.get("token")
                    or ""
                ).strip()
            ),
        "title":
            str(
                payload.get("title")
                or ""
            ),
        "game":
            str(
                payload.get("game")
                or ""
            ),
        "audience_type":
            str(
                payload.get("audience_type")
                or ""
            ),
        "last_stream_id":
            str(
                payload.get("last_stream_id")
                or ""
            ),
        "last_rtmp_host":
            str(
                payload.get("last_rtmp_host")
                or ""
            ),
        "last_rtmp_app":
            str(
                payload.get("last_rtmp_app")
                or ""
            ),
        "last_destination_present":
            bool(
                str(
                    payload.get(
                        "last_destination_url"
                    )
                    or ""
                ).strip()
            ),
        "network_enabled":
            network_enabled(),
    }


def _auth_headers(
    token: str,
) -> dict[str, str]:
    token = str(
        token
        or ""
    ).strip()

    if not token:
        raise StreamlabsProviderError(
            "streamlabs_token_missing"
        )

    return {
        "Authorization":
            f"Bearer {token}",
        "Content-Type":
            "application/json",
        "Accept":
            "application/json",
        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "StreamlabsDesktop/1.20.4 "
                "Chrome/122.0.6261.156 "
                "Electron/29.3.1 "
                "Safari/537.36"
            ),
    }


def _find_destination(
    payload: object,
) -> tuple[str, str]:
    candidates: list[
        dict[str, Any]
    ] = []

    if isinstance(
        payload,
        dict,
    ):
        candidates.append(
            payload
        )

        for key in (
            "data",
            "result",
            "stream",
        ):
            nested = payload.get(
                key
            )

            if isinstance(
                nested,
                dict,
            ):
                candidates.append(
                    nested
                )

    for candidate in candidates:
        base = str(
            candidate.get("rtmp")
            or candidate.get(
                "rtmp_url"
            )
            or candidate.get(
                "server"
            )
            or ""
        ).strip().rstrip("/")

        key = str(
            candidate.get("key")
            or candidate.get(
                "stream_key"
            )
            or ""
        ).strip().lstrip("/")

        if base and key:
            return (
                base,
                key,
            )

    raise StreamlabsProviderError(
        "streamlabs_destination_missing"
    )


def _find_stream_id(
    payload: object,
) -> str:
    if not isinstance(
        payload,
        dict,
    ):
        return ""

    for candidate in (
        payload,
        payload.get("data"),
        payload.get("result"),
        payload.get("stream"),
    ):
        if not isinstance(
            candidate,
            dict,
        ):
            continue

        value = str(
            candidate.get(
                "stream_id"
            )
            or candidate.get("id")
            or ""
        ).strip()

        if value:
            return value

    return ""


def credential_from_payload(
    payload: object,
    *,
    title: str = "",
    game: str = "",
) -> OutputCredential:
    base, key = (
        _find_destination(
            payload
        )
    )

    destination_url = (
        base
        + "/"
        + key
    )

    parsed = urlsplit(
        destination_url
    )

    if parsed.scheme not in {
        "rtmp",
        "rtmps",
    }:
        raise StreamlabsProviderError(
            "streamlabs_destination_scheme_invalid"
        )

    if not parsed.hostname:
        raise StreamlabsProviderError(
            "streamlabs_destination_host_missing"
        )

    return OutputCredential(
        destination_url=
            destination_url,
        provider="streamlabs",
        session_id=
            _find_stream_id(
                payload
            ),
        title=str(
            title
            or ""
        ),
        category=str(
            game
            or ""
        ),
    )


def _multipart_body(
    fields: dict[str, str],
) -> tuple[bytes, str]:
    import uuid

    boundary = (
        "----TikTokLiveV2"
        + uuid.uuid4().hex
    )

    parts: list[bytes] = []

    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\n".encode(
                "utf-8"
            )
        )
        parts.append(
            (
                'Content-Disposition: form-data; '
                f'name="{name}"\r\n\r\n'
            ).encode(
                "utf-8"
            )
        )
        parts.append(
            str(value).encode(
                "utf-8"
            )
        )
        parts.append(
            b"\r\n"
        )

    parts.append(
        f"--{boundary}--\r\n".encode(
            "utf-8"
        )
    )

    return (
        b"".join(parts),
        boundary,
    )


def acquire_with_transport(
    *,
    endpoint: str = "",
    title: str = "",
    game: str = "",
    audience_type: str = "",
    transport: Transport,
) -> OutputCredential:
    if transport is None:
        raise StreamlabsProviderError(
            "streamlabs_transport_missing"
        )

    private = _load_private()

    token = str(
        private.get("token")
        or ""
    ).strip()

    headers = _auth_headers(
        token
    )

    requested_title = str(
        title
        or private.get("title")
        or "Snake Reyers"
    ).strip()

    requested_game = str(
        game
        or private.get("game")
        or ""
    ).strip()

    requested_audience = (
        "1"
        if str(
            audience_type
            or private.get(
                "audience_type"
            )
            or "0"
        )
        == "1"
        else "0"
    )

    fields = {
        "title":
            requested_title,
        "device_platform":
            "win32",
        "category":
            requested_game,
        "audience_type":
            requested_audience,
    }

    body_bytes, boundary = (
        _multipart_body(
            fields
        )
    )

    headers[
        "Content-Type"
    ] = (
        "multipart/form-data; "
        f"boundary={boundary}"
    )

    selected_endpoint = str(
        endpoint
        or (
            STREAMLABS_API_BASE
            + "/stream/start"
        )
    ).strip()

    payload = transport(
        "POST",
        selected_endpoint,
        headers,
        {
            "_multipart":
                body_bytes,
            "_fields":
                fields,
        },
    )

    credential = credential_from_payload(
        payload,
        title=
            requested_title,
        game=
            requested_game,
    )

    details = _destination_details(
        credential.destination_url
    )

    previous_fingerprint = str(
        private.get(
            "last_rtmp_fingerprint"
        )
        or ""
    ).strip()

    _save_private(
        {
            "title":
                requested_title,
            "game":
                requested_game,
            "audience_type":
                requested_audience,
            "last_stream_id":
                credential.session_id,
            "last_destination_url":
                credential.destination_url,
            "previous_rtmp_fingerprint":
                previous_fingerprint,
            "last_rtmp_fingerprint":
                details["fingerprint"],
            "last_rtmp_host":
                details["host"],
            "last_rtmp_app":
                details["app"],
        }
    )

    return credential


def end_stream_with_transport(
    *,
    stream_id: str = "",
    transport: Transport,
) -> dict[str, Any]:
    if transport is None:
        raise StreamlabsProviderError(
            "streamlabs_transport_missing"
        )

    private = _load_private()

    selected_stream_id = str(
        stream_id
        or private.get(
            "last_stream_id"
        )
        or ""
    ).strip()

    if not selected_stream_id:
        return {
            "attempted": False,
            "ended": False,
            "stream_id": "",
            "reason": "stream_id_missing",
        }

    token = str(
        private.get("token")
        or ""
    ).strip()

    headers = _auth_headers(
        token
    )

    endpoint = (
        STREAMLABS_API_BASE
        + "/stream/"
        + quote(
            selected_stream_id,
            safe="",
        )
        + "/end"
    )

    response = transport(
        "POST",
        endpoint,
        headers,
        None,
    )

    ended = not (
        isinstance(
            response,
            dict,
        )
        and response.get("success")
        is False
    )

    if ended:
        _save_private(
            {
                "last_stream_id": "",
                "last_destination_url": "",
            }
        )

    return {
        "attempted": True,
        "ended": bool(ended),
        "stream_id": selected_stream_id,
    }


def end_last_live_with_transport(
    *,
    retries: int = 3,
    delay_seconds: float = 1.5,
    transport: Transport,
) -> dict[str, Any]:
    private = _load_private()
    saved_stream_id = str(
        private.get(
            "last_stream_id"
        )
        or ""
    ).strip()

    total = max(
        1,
        int(retries),
    )
    attempts: list[
        dict[str, Any]
    ] = []

    for attempt in range(
        1,
        total + 1,
    ):
        try:
            result = (
                end_stream_with_transport(
                    stream_id=
                        saved_stream_id,
                    transport=
                        transport,
                )
            )
        except Exception as exc:
            result = {
                "attempted":
                    bool(saved_stream_id),
                "ended": False,
                "stream_id":
                    saved_stream_id,
                "error":
                    f"{type(exc).__name__}:{exc}",
            }

        result["attempt"] = attempt
        attempts.append(
            dict(result)
        )

        if (
            not result.get("attempted")
            or result.get("ended")
        ):
            if len(attempts) > 1:
                result["attempts"] = (
                    attempts
                )
            return result

        if attempt < total:
            time.sleep(
                max(
                    0.1,
                    float(
                        delay_seconds
                    ),
                )
            )

    final = (
        dict(attempts[-1])
        if attempts
        else {
            "attempted": False,
            "ended": False,
            "stream_id": "",
        }
    )
    final["attempts"] = attempts

    refused = bool(
        saved_stream_id
        and all(
            isinstance(
                item,
                dict,
            )
            and "success"
            in str(
                item.get("error")
                or ""
            ).lower()
            and "false"
            in str(
                item.get("error")
                or ""
            ).lower()
            for item in attempts
        )
    )

    if refused:
        _save_private(
            {
                "last_stream_id": "",
                "last_destination_url": "",
            }
        )
        final[
            "cleared_stale_stream_id"
        ] = True

    return final


def public_credential(
    credential: OutputCredential,
) -> dict[str, Any]:
    return {
        "provider":
            credential.provider,
        "session_id":
            credential.session_id,
        "title":
            credential.title,
        "category":
            credential.category,
        "destination":
            public_destination(
                credential.destination_url
            ),
    }
