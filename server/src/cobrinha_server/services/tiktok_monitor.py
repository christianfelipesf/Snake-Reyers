from __future__ import annotations

import json
import os
import socket
import threading
import time
from typing import Any

from cobrinha_server.services import (
    live_events,
    top_supporters,
)
from cobrinha_server.core.settings import (
    TIKTOK_MONITOR_HOST,
    TIKTOK_MONITOR_PORT,
)
from cobrinha_server.services.avatar_cache import cache_profile_avatar
from cobrinha_server.services.tiktok_monitor_runtime import (
    launch_plan as monitor_launch_plan,
    readiness as monitor_runtime_readiness,
    start_local_node,
    stop_local_node,
)


try:
    import socketio as socketio_client
except Exception:
    socketio_client = None


_LOCK = threading.Lock()
_STOP = threading.Event()

_THREAD: threading.Thread | None = None
_CLIENT: Any = None

_GIFT_COMBO_LOCK = threading.Lock()
_ACTIVE_GIFT_COMBOS: dict[str, dict[str, Any]] = {}
_RECENT_GIFT_COMBOS: dict[str, float] = {}


def _env_float(
    name: str,
    default: float,
) -> float:
    try:
        return float(
            os.getenv(
                name,
                str(default),
            )
            or default
        )
    except (
        TypeError,
        ValueError,
    ):
        return float(default)


LISTEN_RETRY_SECONDS = 20.0
EVENT_STALE_RECONNECT_SECONDS = max(
    45.0,
    min(
        900.0,
        _env_float(
            "COBRINHA_TIKTOK_MONITOR_EVENT_STALE_SECONDS",
            150.0,
        ),
    ),
)
EVENT_STALE_GRACE_SECONDS = 45.0
GIFT_COMBO_IDLE_SECONDS = 15.0
GIFT_COMBO_RECENT_SECONDS = 30.0

_STATE: dict[str, Any] = {
    "running": False,
    "connected": False,
    "listening": False,
    "username": "",
    "server_url":
        (
            "http://"
            f"{TIKTOK_MONITOR_HOST}:"
            f"{TIKTOK_MONITOR_PORT}"
        ),
    "last_error": "",
    "last_event": "",
    "last_event_at": 0.0,
    "last_socket_event": "",
    "last_socket_event_at": 0.0,
    "last_listen_at": 0.0,
    "last_gift": {},
    "last_gift_error": "",
    "last_diagnostic": "",
    "reconnect_count": 0,
    "started_at": 0.0,
    "counters": {
        "comment": 0,
        "gift": 0,
        "gift_socket": 0,
        "gift_invalid": 0,
        "gift_duplicate": 0,
        "gift_combo_update": 0,
        "like": 0,
        "share": 0,
    },
}


def _update(
    **values: Any,
) -> None:
    with _LOCK:
        _STATE.update(values)


def _state_snapshot() -> dict[str, Any]:
    with _LOCK:
        return dict(_STATE)


def _count(
    key: str,
) -> None:
    with _LOCK:
        counters = dict(
            _STATE.get(
                "counters"
            )
            or {}
        )

        counters[key] = (
            int(
                counters.get(key)
                or 0
            )
            + 1
        )

        _STATE["counters"] = (
            counters
        )


def _safe_float(
    value: object,
    default: float = 0.0,
) -> float:
    try:
        return float(
            value
            if value is not None
            else default
        )
    except (
        TypeError,
        ValueError,
    ):
        return float(default)


def _friendly_connection_error(
    value: object,
    *,
    username: str,
) -> str:
    message = str(value or "").strip()
    normalized = message.casefold()

    if (
        "failed to retrieve room id"
        in normalized
    ):
        return (
            "Live nao encontrada para @"
            + str(username or "").strip().lstrip("@")
            + ". Confira o usuario e confirme que a live esta online."
        )

    return message


def _mark_socket_event(
    kind: str,
) -> None:
    now = time.time()
    _update(
        last_socket_event=(
            str(kind or "event")
            + " "
            + time.strftime("%H:%M:%S")
        ),
        last_socket_event_at=now,
    )


def _mark_ingested_event(
    kind: str,
) -> None:
    now = time.time()
    label = str(kind or "event")
    _update(
        last_event=(
            label
            + " "
            + time.strftime("%H:%M:%S")
        ),
        last_event_at=now,
        last_socket_event=(
            label
            + " "
            + time.strftime("%H:%M:%S")
        ),
        last_socket_event_at=now,
        last_error="",
    )


def tor_socks_listening(
    host: str = "127.0.0.1",
    port: int = 9050,
    timeout: float = 0.35,
) -> bool:
    try:
        with socket.create_connection(
            (
                host,
                int(port),
            ),
            timeout=max(
                0.05,
                float(timeout),
            ),
        ):
            return True
    except OSError:
        return False


def status() -> dict[str, Any]:
    with _LOCK:
        state = dict(_STATE)

    state["counters"] = dict(
        state.get("counters")
        or {}
    )

    state["available"] = (
        socketio_client
        is not None
    )

    state["thread_alive"] = bool(
        _THREAD
        and _THREAD.is_alive()
    )

    runtime = (
        monitor_runtime_readiness()
    )

    state["runtime"] = runtime
    state["launch_plan"] = (
        monitor_launch_plan()
    )

    state["network"] = {
        "required": "tor",
        "socks_host":
            str(
                runtime
                .get("tor", {})
                .get(
                    "host",
                    "127.0.0.1",
                )
            ),
        "socks_port":
            int(
                runtime
                .get("tor", {})
                .get(
                    "port",
                    9050,
                )
            ),
        "socks_listening":
            bool(
                runtime
                .get("tor", {})
                .get(
                    "socks_listening"
                )
            ),
    }

    # Importante: este modulo nao inicia Tor,
    # nao inicia transmissao e nao inicia sozinho.
    state["auto_start"] = False

    return state


def start_monitor(
    username: str,
    *,
    server_url: str = (
        "http://127.0.0.1:2619"
    ),
    prepare_local_node: bool = False,
) -> dict[str, Any]:
    global _THREAD

    clean_username = str(
        username or ""
    ).strip().lstrip("@")

    clean_server_url = str(
        server_url
        or (
            "http://"
            f"{TIKTOK_MONITOR_HOST}:"
            f"{TIKTOK_MONITOR_PORT}"
        )
    ).strip()

    if not clean_username:
        _update(
            running=False,
            last_error=(
                "Usuario TikTok vazio."
            ),
        )
        return status()

    if socketio_client is None:
        _update(
            running=False,
            last_error=(
                "Dependencia ausente: "
                "python-socketio[client]."
            ),
        )
        return status()

    runtime = (
        monitor_runtime_readiness()
    )

    if (
        prepare_local_node
        and not bool(
            (
                runtime.get(
                    "local_server"
                )
                or {}
            ).get(
                "listening"
            )
        )
    ):
        node_start = start_local_node(
            execute=True
        )

        runtime = (
            monitor_runtime_readiness()
        )

        if not node_start.get("ok"):
            _update(
                running=False,
                connected=False,
                listening=False,
                username=clean_username,
                server_url=
                    clean_server_url,
                last_error=(
                    "Falha ao preparar o "
                    "servidor Node local: "
                    + str(
                        node_start.get(
                            "reason"
                        )
                        or "desconhecida"
                    )
                ),
                node_prepare=
                    node_start,
            )

            return status()

    if not runtime.get(
        "source_ready"
    ):
        _update(
            running=False,
            connected=False,
            listening=False,
            username=clean_username,
            server_url=clean_server_url,
            last_error=(
                "Fonte local do monitor TikTok "
                "nao esta completa."
            ),
        )
        return status()

    if not runtime.get(
        "binaries_ready"
    ):
        _update(
            running=False,
            connected=False,
            listening=False,
            username=clean_username,
            server_url=clean_server_url,
            last_error=(
                "Node ou torsocks nao esta "
                "disponivel para o monitor."
            ),
        )
        return status()

    if not runtime.get(
        "dependencies_ready"
    ):
        _update(
            running=False,
            connected=False,
            listening=False,
            username=clean_username,
            server_url=clean_server_url,
            last_error=(
                "Dependencias Node do monitor "
                "TikTok ainda nao estao instaladas."
            ),
        )
        return status()

    if not runtime.get(
        "tor_ready"
    ):
        _update(
            running=False,
            connected=False,
            listening=False,
            username=clean_username,
            server_url=clean_server_url,
            last_error=(
                "Tor SOCKS nao esta disponivel. "
                "Rede direta continua bloqueada."
            ),
        )
        return status()

    local_server = (
        runtime.get("local_server")
        if isinstance(
            runtime.get("local_server"),
            dict,
        )
        else {}
    )

    if not bool(
        local_server.get("listening")
    ):
        _update(
            running=False,
            connected=False,
            listening=False,
            username=clean_username,
            server_url=clean_server_url,
            last_error=(
                "Servidor Node local do monitor "
                "ainda nao esta ativo. "
                "Nenhuma conexao TikTok foi aberta."
            ),
        )
        return status()

    if not tor_socks_listening():
        _update(
            running=False,
            connected=False,
            listening=False,
            username=clean_username,
            server_url=
                clean_server_url,
            last_error=(
                "Tor SOCKS 127.0.0.1:9050 "
                "nao esta disponivel. "
                "O monitor nao foi iniciado."
            ),
        )
        return status()

    with _LOCK:
        current_thread = _THREAD

    if (
        current_thread
        and current_thread.is_alive()
    ):
        current = status()

        same_target = (
            str(
                current.get(
                    "username"
                )
                or ""
            )
            == clean_username
            and str(
                current.get(
                    "server_url"
                )
                or ""
            )
            == clean_server_url
        )

        if same_target:
            return current

        stop_monitor()

    _STOP.clear()
    _reset_gift_combo_tracking()

    _THREAD = threading.Thread(
        target=_loop,
        args=(
            clean_username,
            clean_server_url,
        ),
        daemon=True,
        name=(
            "cobrinha-tiktok-monitor"
        ),
    )

    _THREAD.start()

    _update(
        running=True,
        connected=False,
        listening=False,
        username=clean_username,
        server_url=
            clean_server_url,
        last_error=(
            "Monitor iniciando."
        ),
        started_at=time.time(),
        last_event="",
        last_event_at=0.0,
        last_socket_event="",
        last_socket_event_at=0.0,
        last_listen_at=0.0,
        last_gift={},
        last_gift_error="",
        last_diagnostic="",
        reconnect_count=0,
        counters={
            "comment": 0,
            "gift": 0,
            "gift_socket": 0,
            "gift_invalid": 0,
            "gift_duplicate": 0,
            "gift_combo_update": 0,
            "like": 0,
            "share": 0,
        },
    )

    return status()


def stop_monitor(
    *,
    stop_local_node_runtime: bool = False,
) -> dict[str, Any]:
    global _THREAD

    _STOP.set()
    _disconnect()

    thread = _THREAD

    if (
        thread is not None
        and thread
        is not threading.current_thread()
    ):
        thread.join(
            timeout=3.0
        )

    if (
        thread is None
        or not thread.is_alive()
    ):
        _THREAD = None

    node_stop: dict[str, Any] = {}

    if stop_local_node_runtime:
        node_stop = stop_local_node(
            execute=True
        )

    _update(
        running=False,
        connected=False,
        listening=False,
        last_error=(
            "Monitor parado."
        ),
        node_stop=node_stop,
    )

    return status()


def _loop(
    username: str,
    server_url: str,
) -> None:
    global _CLIENT

    while not _STOP.is_set():
        if socketio_client is None:
            _update(
                running=False,
                connected=False,
                listening=False,
                last_error=(
                    "Dependencia ausente: "
                    "python-socketio[client]."
                ),
            )
            return

        if not tor_socks_listening():
            _update(
                running=True,
                connected=False,
                listening=False,
                last_error=(
                    "Tor SOCKS indisponivel."
                ),
            )

            if _STOP.wait(8.0):
                break

            continue

        client = (
            socketio_client.Client(
                reconnection=True,
                reconnection_attempts=5,
                reconnection_delay=2,
                logger=False,
                engineio_logger=False,
            )
        )

        _CLIENT = client

        _register_handlers(
            client,
            username,
        )

        try:
            _update(
                running=True,
                connected=False,
                listening=False,
                last_error=(
                    "Conectando ao monitor "
                    "TikTok local."
                ),
            )

            transports = [
                "polling",
            ]

            try:
                import websocket  # type: ignore  # noqa: F401

                transports = [
                    "websocket",
                    "polling",
                ]
            except ImportError:
                pass

            client.connect(
                server_url,
                transports=transports,
                wait_timeout=12,
            )

            not_listening_since = (
                time.time()
            )
            last_stale_reconnect_at = 0.0

            while not _STOP.wait(
                2.0
            ):
                if not getattr(
                    client,
                    "connected",
                    False,
                ):
                    break

                current = _state_snapshot()
                now = time.time()
                if bool(
                    current.get(
                        "listening"
                    )
                ):
                    not_listening_since = (
                        now
                    )

                    last_flow_at = max(
                        _safe_float(
                            current.get(
                                "last_socket_event_at"
                            )
                        ),
                        _safe_float(
                            current.get(
                                "last_event_at"
                            )
                        ),
                        _safe_float(
                            current.get(
                                "last_listen_at"
                            )
                        ),
                        _safe_float(
                            current.get(
                                "started_at"
                            )
                        ),
                    )
                    listen_age = (
                        now
                        - max(
                            _safe_float(
                                current.get(
                                    "last_listen_at"
                                )
                            ),
                            _safe_float(
                                current.get(
                                    "started_at"
                                )
                            ),
                        )
                    )
                    stale_age = (
                        now
                        - last_flow_at
                        if last_flow_at > 0.0
                        else 0.0
                    )

                    if (
                        listen_age
                        >= EVENT_STALE_GRACE_SECONDS
                        and stale_age
                        >= EVENT_STALE_RECONNECT_SECONDS
                        and now
                        - last_stale_reconnect_at
                        >= EVENT_STALE_RECONNECT_SECONDS
                    ):
                        last_stale_reconnect_at = now
                        reconnect_count = int(
                            current.get(
                                "reconnect_count"
                            )
                            or 0
                        ) + 1
                        _update(
                            running=True,
                            connected=True,
                            listening=False,
                            reconnect_count=
                                reconnect_count,
                            last_error=(
                                "Monitor sem eventos "
                                f"ha {stale_age:.0f}s; "
                                "reconectando somente "
                                "o monitor TikTok."
                            ),
                        )
                        break

                    continue

                not_listening_age = (
                    now - not_listening_since
                )
                if (
                    not_listening_age
                    >= LISTEN_RETRY_SECONDS
                ):
                    last_error = str(
                        current.get(
                            "last_error"
                        )
                        or (
                            "Monitor nao entrou "
                            "em modo de escuta."
                        )
                    )
                    _update(
                        running=True,
                        connected=True,
                        listening=False,
                        last_error=(
                            last_error
                            + " Reconectando "
                            "monitor local."
                        ),
                    )
                    break

        except Exception as exc:
            if not _STOP.is_set():
                _update(
                    running=True,
                    connected=False,
                    listening=False,
                    last_error=(
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                )

                _STOP.wait(8.0)

        finally:
            _disconnect_client(
                client
            )

    _update(
        running=False,
        connected=False,
        listening=False,
    )


def _disconnect() -> None:
    client = _CLIENT

    if client is not None:
        _disconnect_client(
            client
        )


def _disconnect_client(
    client: Any,
) -> None:
    try:
        if getattr(
            client,
            "connected",
            False,
        ):
            client.disconnect()
    except Exception:
        pass


def _parse_payload(
    raw: object,
) -> dict[str, Any]:
    if isinstance(
        raw,
        dict,
    ):
        return dict(raw)

    if isinstance(
        raw,
        str,
    ):
        try:
            value = json.loads(raw)
        except Exception:
            return {}

        if isinstance(
            value,
            dict,
        ):
            return value

    return {}


def _nested(
    data: dict[str, Any],
    path: str,
) -> Any:
    current: Any = data

    for part in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
            continue

        if not isinstance(
            current,
            dict,
        ):
            return None

        current = current.get(part)

    return current


def _first(
    data: dict[str, Any],
    *paths: str,
) -> Any:
    for path in paths:
        value = _nested(
            data,
            path,
        )

        if value not in {
            None,
            "",
        }:
            return value

    return None


def _safe_int(
    value: object,
    default: int = 0,
) -> int:
    try:
        return int(
            float(
                value
                if value is not None
                else default
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return int(default)


def _username(
    data: dict[str, Any],
) -> str:
    return str(
        _first(
            data,
            "uniqueId",
            "unique_id",
            "username",
            "displayId",
            "display_id",
            "user.uniqueId",
            "user.unique_id",
            "user.username",
            "user.displayId",
            "user.display_id",
            "userDetails.uniqueId",
            "userDetails.unique_id",
            "userDetails.username",
            "userDetails.displayId",
            "userDetails.display_id",
            "userInfo.user.uniqueId",
            "userInfo.user.unique_id",
            "userInfo.user.username",
            "userInfo.user.displayId",
            "userInfo.user.display_id",
        )
        or ""
    ).strip().lstrip("@")


def _user_id(
    data: dict[str, Any],
) -> str:
    return str(
        _first(
            data,
            "userId",
            "user_id",
            "id",
            "idStr",
            "secUid",
            "user.userId",
            "user.user_id",
            "user.id",
            "user.idStr",
            "user.secUid",
            "userDetails.userId",
            "userDetails.user_id",
            "userDetails.id",
            "userDetails.idStr",
            "userDetails.secUid",
            "userInfo.user.userId",
            "userInfo.user.user_id",
            "userInfo.user.id",
            "userInfo.user.idStr",
            "userInfo.user.secUid",
        )
        or _username(data)
    ).strip()


def _display_name(
    data: dict[str, Any],
) -> str:
    return str(
        _first(
            data,
            "nickname",
            "displayName",
            "display_name",
            "user.nickname",
            "user.displayName",
            "user.display_name",
            "userDetails.nickname",
            "userDetails.displayName",
            "userDetails.display_name",
            "userInfo.user.nickname",
            "userInfo.user.displayName",
            "userInfo.user.display_name",
        )
        or _username(data)
    ).strip()


def _profile_image(
    data: dict[str, Any],
) -> str:
    direct = _first(
        data,
        "profilePictureUrl",
        "profile_image",
        "avatar_url",
        "user.profilePictureUrl",
        "user.profile_image",
        "user.avatar_url",
        "user.avatarThumb.urlList.0",
        "userDetails.profilePictureUrl",
        "userDetails.profilePictureUrls.0",
        "userDetails.profile_image",
        "userDetails.avatar_url",
        "userDetails.avatarThumb.urlList.0",
        "userInfo.user.profilePictureUrl",
        "userInfo.user.profilePictureUrls.0",
        "userInfo.user.profile_image",
        "userInfo.user.avatar_url",
        "userInfo.user.avatarThumb.urlList.0",
        "avatarThumb.urlList.0",
    )

    if direct:
        return str(
            direct
        ).strip()

    avatar_thumb = _nested(
        data,
        "user.avatarThumb",
    )

    if isinstance(
        avatar_thumb,
        dict,
    ):
        url_list = (
            avatar_thumb.get("urlList")
            or avatar_thumb.get("url_list")
            or []
        )

        if (
            isinstance(url_list, list)
            and url_list
        ):
            return str(
                url_list[0]
                or ""
            ).strip()

    return ""


def _avatar_path_for_payload(
    payload: dict[str, Any],
) -> str:
    existing_path = str(
        payload.get("avatar_path")
        or ""
    ).strip()
    if existing_path:
        return existing_path

    avatar_url = str(
        payload.get("avatar_url")
        or payload.get("profile_image")
        or ""
    ).strip()
    if not avatar_url:
        return ""

    user_key = str(
        payload.get("user_id")
        or payload.get("username")
        or payload.get("display_name")
        or ""
    ).strip()
    result = cache_profile_avatar(
        avatar_url,
        user_key=user_key,
        timeout=3.0,
    )
    if not result.get("ok"):
        return ""
    return str(result.get("path") or "").strip()


def _comment_text(
    data: dict[str, Any],
) -> str:
    return str(
        _first(
            data,
            "comment",
            "message",
            "text",
            "content",
            "chatMessage.comment",
            "chatMessage.content",
        )
        or ""
    ).strip()


def _gift_name(
    data: dict[str, Any],
) -> str:
    return str(
        _first(
            data,
            "giftName",
            "gift_name",
            "gift.name",
            "giftDetails.giftName",
            "giftDetails.name",
            "giftDetails.title",
        )
        or ""
    ).strip()


def _gift_count(
    data: dict[str, Any],
) -> int:
    return (
        live_events.gift_count(
            data
        )
    )


def _gift_coin_value(
    data: dict[str, Any],
) -> int:
    return (
        live_events.gift_coin_value(
            data
        )
    )


def _gift_combo_value(
    data: dict[str, Any],
    *paths: str,
) -> str:
    return str(
        _first(
            data,
            *paths,
        )
        or ""
    ).strip()


def _gift_combo_key(
    data: dict[str, Any],
) -> tuple[str, bool]:
    user_key = (
        _user_id(data)
        or _username(data)
    ).strip().casefold()
    gift_key = (
        _gift_combo_value(
            data,
            "giftId",
            "gift_id",
            "gift.gift_id",
        )
        or _gift_name(data).casefold()
    )
    combo_id = _gift_combo_value(
        data,
        "groupId",
        "group_id",
        "gift.groupId",
        "gift.group_id",
    )
    base_key = f"{user_key}|{gift_key}"
    if combo_id and combo_id != "0":
        return f"{base_key}|{combo_id}", True
    return base_key, False


def _gift_combo_fields(
    data: dict[str, Any],
) -> tuple[int, bool]:
    gift_type = _safe_int(
        _first(
            data,
            "giftType",
            "gift_type",
            "gift.giftType",
            "gift.gift_type",
            "giftDetails.giftType",
            "giftDetails.gift_type",
            "giftDetails.type",
        ),
        0,
    )
    repeat_end_value = _first(
        data,
        "repeatEnd",
        "repeat_end",
        "gift.repeatEnd",
        "gift.repeat_end",
        "giftDetails.repeatEnd",
        "giftDetails.repeat_end",
    )
    repeat_end = repeat_end_value in {
        True,
        1,
        "1",
        "true",
        "True",
    }
    return gift_type, repeat_end


def _reset_gift_combo_tracking() -> None:
    with _GIFT_COMBO_LOCK:
        _ACTIVE_GIFT_COMBOS.clear()
        _RECENT_GIFT_COMBOS.clear()


def _should_ingest_gift_combo_update(
    data: dict[str, Any],
    *,
    now: float | None = None,
) -> tuple[bool, str]:
    gift_type, repeat_end = _gift_combo_fields(data)
    if gift_type != 1:
        return True, "gift_not_streakable"

    current_time = time.time() if now is None else float(now)
    combo_key, has_explicit_combo_id = _gift_combo_key(data)
    count = _gift_count(data)

    with _GIFT_COMBO_LOCK:
        expired_active = [
            key
            for key, item in _ACTIVE_GIFT_COMBOS.items()
            if current_time - float(item.get("last_at") or 0.0)
            > GIFT_COMBO_IDLE_SECONDS
        ]
        for key in expired_active:
            _ACTIVE_GIFT_COMBOS.pop(key, None)

        expired_recent = [
            key
            for key, closed_at in _RECENT_GIFT_COMBOS.items()
            if current_time - float(closed_at or 0.0)
            > GIFT_COMBO_RECENT_SECONDS
        ]
        for key in expired_recent:
            _RECENT_GIFT_COMBOS.pop(key, None)

        active = _ACTIVE_GIFT_COMBOS.get(combo_key)
        if repeat_end:
            if active is not None:
                _ACTIVE_GIFT_COMBOS.pop(combo_key, None)
                _RECENT_GIFT_COMBOS[combo_key] = current_time
                return False, "gift_combo_finished"
            if combo_key in _RECENT_GIFT_COMBOS:
                return False, "gift_combo_final_duplicate"

            # If the monitor connected in the middle of a combo, its final
            # packet is the first one we can act on.
            _RECENT_GIFT_COMBOS[combo_key] = current_time
            return True, "gift_combo_final_first_seen"

        if active is not None:
            active["last_at"] = current_time
            active["max_count"] = max(
                int(active.get("max_count") or 1),
                count,
            )
            return False, "gift_combo_progress"

        if has_explicit_combo_id and combo_key in _RECENT_GIFT_COMBOS:
            return False, "gift_combo_closed_duplicate"

        # Without a TikTok group id, the final packet closes the previous
        # combo and a new count=1 packet must be accepted immediately.
        _RECENT_GIFT_COMBOS.pop(combo_key, None)
        _ACTIVE_GIFT_COMBOS[combo_key] = {
            "started_at": current_time,
            "last_at": current_time,
            "max_count": count,
        }
        return True, "gift_combo_started"


def normalize_comment_payload(
    raw: object,
) -> dict[str, Any]:
    data = _parse_payload(raw)

    return {
        "user_id":
            _user_id(data),
        "username":
            _username(data),
        "display_name":
            _display_name(data),
        "avatar_url":
            _profile_image(data),
        "profile_image":
            _profile_image(data),
        "avatar_path":
            str(_first(data, "avatar_path") or "").strip(),
        "comment":
            _comment_text(data),
        "text":
            _comment_text(data),
        "source": "tiktok",
    }


def normalize_gift_payload(
    raw: object,
) -> dict[str, Any]:
    data = _parse_payload(raw)

    count = _gift_count(
        data
    )

    coin_value = _gift_coin_value(
        data
    )

    event_id = str(
        _first(
            data,
            "msgId",
            "msg_id",
            "messageId",
            "message_id",
            "eventId",
            "event_id",
            "common.msgId",
            "common.msg_id",
            "common.messageId",
            "common.message_id",
        )
        or ""
    ).strip()
    if event_id == "0":
        event_id = ""

    gift_type, repeat_end = _gift_combo_fields(data)
    combo_id = _gift_combo_value(
        data,
        "groupId",
        "group_id",
        "gift.groupId",
        "gift.group_id",
        "giftDetails.groupId",
        "giftDetails.group_id",
    )
    gift_id = _gift_combo_value(
        data,
        "giftId",
        "gift_id",
        "gift.gift_id",
        "giftDetails.giftId",
        "giftDetails.gift_id",
        "giftDetails.id",
    )

    return {
        "user_id":
            _user_id(data),
        "username":
            _username(data),
        "display_name":
            _display_name(data),
        "avatar_url":
            _profile_image(data),
        "profile_image":
            _profile_image(data),
        "avatar_path":
            str(_first(data, "avatar_path") or "").strip(),
        "gift_name":
            _gift_name(data),
        "count":
            count,
        "coin_value":
            coin_value,
        "gift_total_coins":
            coin_value
            * count,
        "event_id": event_id,
        "combo_id": combo_id,
        "gift_id": gift_id,
        "gift_type": gift_type,
        "repeat_end": repeat_end,
        "cannon_only": bool(data.get("cannon_only", False)),
        "suppress_gift_cannon": bool(
            data.get("suppress_gift_cannon", False)
        ),
        "source": "tiktok",
    }


def _activity_count(
    data: dict[str, Any],
    *paths: str,
) -> int:
    return max(
        1,
        _safe_int(
            _first(
                data,
                *paths,
            ),
            1,
        ),
    )


def normalize_like_payload(
    raw: object,
) -> dict[str, Any]:
    data = _parse_payload(raw)
    return {
        "user_id":
            _user_id(data),
        "username":
            _username(data),
        "display_name":
            _display_name(data),
        "avatar_url":
            _profile_image(data),
        "profile_image":
            _profile_image(data),
        "avatar_path":
            str(_first(data, "avatar_path") or "").strip(),
        "count":
            _activity_count(
                data,
                "count",
                "likeCount",
                "like_count",
                "likes",
            ),
        "source": "tiktok",
    }


def normalize_share_payload(
    raw: object,
) -> dict[str, Any]:
    data = _parse_payload(raw)
    return {
        "user_id":
            _user_id(data),
        "username":
            _username(data),
        "display_name":
            _display_name(data),
        "avatar_url":
            _profile_image(data),
        "profile_image":
            _profile_image(data),
        "avatar_path":
            str(_first(data, "avatar_path") or "").strip(),
        "count":
            _activity_count(
                data,
                "count",
                "shareCount",
                "share_count",
            ),
        "source": "tiktok",
    }


def ingest_comment(
    raw: object,
) -> dict[str, Any]:
    payload = (
        normalize_comment_payload(
            raw
        )
    )

    if (
        not payload["username"]
        or not payload["comment"]
    ):
        return {
            "ok": False,
            "ignored": True,
            "reason":
                "comment_incompleto",
        }

    event = (
        live_events.push_comment(
            payload
        )
    )

    if event.get("ignored"):
        return {
            "ok": True,
            "ignored": True,
            "reason":
                event.get(
                    "reason"
                )
                or "ignored_comment",
            "event": event,
        }

    _count("comment")
    _mark_ingested_event("comment")

    return {
        "ok": True,
        "event": event,
    }


def ingest_gift(
    raw: object,
) -> dict[str, Any]:
    payload = (
        normalize_gift_payload(
            raw
        )
    )

    if (
        not payload["username"]
        or not payload["gift_name"]
    ):
        _count("gift_invalid")
        _update(
            last_gift_error="Presente recebido sem usuario ou nome.",
            last_gift={
                "username": str(payload.get("username") or ""),
                "gift_name": str(payload.get("gift_name") or ""),
            },
        )
        return {
            "ok": False,
            "ignored": True,
            "reason":
                "gift_incompleto",
        }

    event = (
        live_events.push_gift(
            payload
        )
    )

    if event.get("ignored"):
        if event.get("reason") == "duplicate_gift":
            _count("gift_duplicate")
        return {
            "ok": True,
            "ignored": True,
            "reason": event.get("reason") or "ignored_gift",
            "event": event,
        }

    payload["avatar_path"] = (
        _avatar_path_for_payload(
            payload
        )
    )
    if payload["avatar_path"]:
        event["avatar_path"] = payload["avatar_path"]

    if not bool(payload.get("cannon_only", False)):
        top_supporters.record_gift(event)

    _count("gift")
    _update(
        last_gift={
            "username": str(payload.get("username") or ""),
            "display_name": str(payload.get("display_name") or ""),
            "gift_name": str(payload.get("gift_name") or ""),
            "count": int(payload.get("count") or 1),
            "coin_value": int(payload.get("coin_value") or 0),
            "received_at": time.time(),
        },
        last_gift_error="",
    )
    _mark_ingested_event("gift")

    return {
        "ok": True,
        "event": event,
    }


def ingest_tiktok_gift(
    raw: object,
) -> dict[str, Any]:
    data = _parse_payload(raw)
    should_ingest, reason = _should_ingest_gift_combo_update(data)
    if should_ingest:
        payload = normalize_gift_payload(data)
        if reason == "gift_combo_started":
            identity = (
                str(payload.get("combo_id") or "").strip()
                or str(payload.get("event_id") or "").strip()
                or str(time.time_ns())
            )
            payload["event_id"] = f"cannon:{identity}"
            payload["cannon_only"] = True
        return ingest_gift(payload)

    if reason == "gift_combo_finished":
        payload = normalize_gift_payload(data)
        payload["suppress_gift_cannon"] = True
        return ingest_gift(payload)

    _count("gift_combo_update")
    return {
        "ok": True,
        "ignored": True,
        "reason": reason,
    }


def ingest_like(
    raw: object,
) -> dict[str, Any]:
    payload = (
        normalize_like_payload(
            raw
        )
    )

    if not payload["username"]:
        return {
            "ok": False,
            "ignored": True,
            "reason": "like_incompleto",
        }

    payload["avatar_path"] = (
        _avatar_path_for_payload(
            payload
        )
    )

    result = top_supporters.record_like(
        payload
    )
    _count("like")
    _mark_ingested_event("like")
    return {
        "ok": bool(result.get("ok")),
        "activity": result,
    }


def ingest_share(
    raw: object,
) -> dict[str, Any]:
    payload = (
        normalize_share_payload(
            raw
        )
    )

    if not payload["username"]:
        return {
            "ok": False,
            "ignored": True,
            "reason": "share_incompleto",
        }

    payload["avatar_path"] = (
        _avatar_path_for_payload(
            payload
        )
    )

    result = top_supporters.record_share(
        payload
    )
    _count("share")
    _mark_ingested_event("share")
    return {
        "ok": bool(result.get("ok")),
        "activity": result,
    }


def _register_handlers(
    client: Any,
    username: str,
) -> None:
    @client.event
    def connect() -> None:
        _update(
            running=True,
            connected=True,
            listening=False,
            last_error="",
        )

        client.emit(
            "listenToUsername",
            json.dumps(
                {
                    "username":
                        username,
                    "proxy": True,
                }
            ),
        )

    @client.event
    def disconnect() -> None:
        _update(
            connected=False,
            listening=False,
        )

    @client.on(
        "data-connection"
    )
    def on_data_connection(
        raw: object,
    ) -> None:
        data = _parse_payload(
            raw
        )

        listening = bool(
            data.get(
                "isConnected"
            )
        )
        now = time.time()

        _update(
            running=True,
            connected=True,
            listening=listening,
            last_listen_at=(
                now
                if listening
                else _safe_float(
                    _state_snapshot().get(
                        "last_listen_at"
                    )
                )
            ),
            last_error=(
                ""
                if listening
                else _friendly_connection_error(
                    data.get("message")
                    or "Monitor aguardando live.",
                    username=username,
                )
            ),
        )

    @client.on(
        "data-chat"
    )
    def on_chat(
        raw: object,
    ) -> None:
        _mark_socket_event("comment")
        ingest_comment(raw)

    @client.on(
        "data-gift"
    )
    def on_gift(
        raw: object,
    ) -> None:
        _count("gift_socket")
        _mark_socket_event("gift")
        data = _parse_payload(
            raw
        )

        ingest_tiktok_gift(data)

    @client.on(
        "data-monitor-diagnostic"
    )
    def on_monitor_diagnostic(
        raw: object,
    ) -> None:
        data = _parse_payload(raw)
        message = str(
            data.get("message")
            or data.get("error")
            or "Diagnostico do monitor sem detalhes."
        ).strip()
        _update(last_diagnostic=message)

    @client.on(
        "data-like"
    )
    def on_like(
        raw: object,
    ) -> None:
        _mark_socket_event("like")
        ingest_like(raw)

    @client.on(
        "data-share"
    )
    def on_share(
        raw: object,
    ) -> None:
        _mark_socket_event("share")
        ingest_share(raw)
