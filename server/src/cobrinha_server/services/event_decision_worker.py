from __future__ import annotations

import asyncio
import hashlib
import re
import time
import unicodedata
import uuid
from typing import Any

from cobrinha_server.bridge.godot_bridge import godot_bridge
from cobrinha_server.core.json_store import read_json, write_json_atomic
from cobrinha_server.core.settings import RUNS_DIR
from cobrinha_server.services import (
    content_updates,
    godot_runtime_state,
    live_events,
    song_runtime,
    top_supporters,
)
from cobrinha_server.services.avatar_cache import cache_profile_avatar
from cobrinha_server.services.social_dispatcher import gift_apples_message
from cobrinha_server.services.social_events import spectator_user_message
from cobrinha_server.services.social_reply import (
    build_gift_reply,
    build_main_reply,
)
from cobrinha_server.services.speech_queue import enqueue_text, status as speech_queue_status
from cobrinha_server.services.tts_worker import worker_status as tts_worker_status


WORKER_STATUS_FILE = RUNS_DIR / "event_decision_worker_status.json"
CURRENT_GAME = "Cobrinha"
GIFT_GROUP_THANK_WINDOW_SECONDS = 4.0
GIFT_GROUP_THANK_MIN_EVENTS = 4
GIFT_GROUP_THANK_FLUSH_MIN_EVENTS = 2
GIFT_INDIVIDUAL_THANK_COOLDOWN_SECONDS = 18.0
GIFT_HIGH_VALUE_COINS = 100
HEART_ME_BAND_GIFT_KEYS = {
    "heart-me",
    "heartme",
    "hartme",
    "hatme",
}

_TASK: asyncio.Task[None] | None = None
_GIFT_THANK_BUFFER: list[dict[str, Any]] = []
_LAST_GIFT_THANK_AT_BY_KEY: dict[str, float] = {}
_STATE: dict[str, Any] = {
    "running": False,
    "task_alive": False,
    "last_action": "",
    "last_error": "",
    "events_processed": 0,
    "comments_processed": 0,
    "gifts_processed": 0,
    "updated_at": 0.0,
}


def _write_status(**values: Any) -> None:
    _STATE.update(values)
    _STATE["task_alive"] = bool(_TASK and not _TASK.done())
    _STATE["updated_at"] = time.time()
    write_json_atomic(WORKER_STATUS_FILE, dict(_STATE))


def status() -> dict[str, Any]:
    stored = read_json(WORKER_STATUS_FILE, {})
    public = dict(stored) if isinstance(stored, dict) else {}
    task_alive = bool(_TASK and not _TASK.done())
    return {
        **_STATE,
        **public,
        "running": task_alive,
        "task_alive": task_alive,
    }


def reset_transient_state(
    *,
    reason: str = "live_session_reset",
) -> dict[str, Any]:
    _GIFT_THANK_BUFFER.clear()
    _LAST_GIFT_THANK_AT_BY_KEY.clear()
    _write_status(
        running=bool(_TASK and not _TASK.done()),
        last_action=str(reason or "live_session_reset"),
        last_error="",
        events_processed=0,
        comments_processed=0,
        gifts_processed=0,
    )
    return status()


def start_event_decision_worker() -> dict[str, Any]:
    global _TASK

    if _TASK is not None and not _TASK.done():
        return status()

    _TASK = asyncio.create_task(
        _loop(),
        name="cobrinha-event-decision-worker",
    )
    _write_status(running=True, last_action="started", last_error="")
    return status()


async def stop_event_decision_worker() -> dict[str, Any]:
    global _TASK

    task = _TASK
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    _TASK = None
    _write_status(running=False, last_action="stopped")
    return status()


async def _loop() -> None:
    try:
        while True:
            try:
                await process_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _write_status(
                    running=True,
                    last_action="loop_error",
                    last_error=f"{type(exc).__name__}: {exc}",
                )
                await asyncio.sleep(1.0)
                continue

            await asyncio.sleep(0.18)
    except asyncio.CancelledError:
        raise
    finally:
        _write_status(running=False)


def _speech_pipeline_can_accept_next() -> bool:
    if song_runtime.singing_blocks_speech():
        return False

    if godot_runtime_state.heart_me_band_music_showcase_active():
        return False

    queue_state = speech_queue_status()
    manual_sequence = (
        queue_state.get("manual_sequence")
        if isinstance(queue_state.get("manual_sequence"), dict)
        else {}
    )
    if bool(manual_sequence.get("active")):
        return False

    if queue_state.get("active"):
        return False
    if int(queue_state.get("pending_size") or 0) > 0:
        return False
    if int(queue_state.get("pair_waiting_size") or 0) > 0:
        return False
    if int(queue_state.get("ready_size") or 0) > 0:
        return False

    worker = tts_worker_status()
    if str(worker.get("state") or "").strip() == "preparing":
        return False

    return True


def _event_user_key(event: dict[str, Any]) -> str:
    return str(
        event.get("user_id")
        or event.get("username")
        or event.get("display_name")
        or ""
    ).strip()


def _snake_color_for_user(user_key: str) -> str:
    digest = hashlib.sha256(str(user_key or "").encode("utf-8", errors="ignore")).digest()
    hue = int.from_bytes(digest[:2], "big") / 65535.0
    saturation = 0.72
    value = 0.94
    channel = int(hue * 6.0)
    fraction = hue * 6.0 - channel
    p = value * (1.0 - saturation)
    q = value * (1.0 - fraction * saturation)
    t = value * (1.0 - (1.0 - fraction) * saturation)
    channel %= 6
    rgb = (
        (value, t, p),
        (q, value, p),
        (p, value, t),
        (p, q, value),
        (t, p, value),
        (value, p, q),
    )[channel]
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(part * 255))) for part in rgb)


async def _cache_avatar_for_event(event: dict[str, Any]) -> str:
    existing_path = str(event.get("avatar_path") or "").strip()
    if existing_path:
        return existing_path

    avatar_url = str(event.get("avatar_url") or event.get("profile_image") or "").strip()
    if not avatar_url:
        return ""

    result = await asyncio.to_thread(
        cache_profile_avatar,
        avatar_url,
        user_key=_event_user_key(event),
    )
    if not result.get("ok"):
        return ""
    return str(result.get("path") or "").strip()


async def _send_spectator_activity(
    event: dict[str, Any],
    *,
    source: str,
) -> str:
    avatar_path = await _cache_avatar_for_event(event)
    user_key = _event_user_key(event)
    message = spectator_user_message(
        {
            "user_id": event.get("user_id"),
            "username": event.get("username"),
            "display_name": event.get("display_name"),
            "avatar_url": event.get("avatar_url") or event.get("profile_image"),
            "comment": event.get("text"),
        },
        avatar_path=avatar_path,
        source=source,
        preview=False,
    )
    payload = message.setdefault("payload", {})
    if isinstance(payload, dict):
        payload["snake_color"] = _snake_color_for_user(user_key)
        payload["slot_limit"] = 16
        payload["activity_kind"] = str(event.get("kind") or "")
    await godot_bridge.send(message)
    return avatar_path


def _display_name(event: dict[str, Any]) -> str:
    return str(event.get("display_name") or event.get("username") or "visitante").strip()


def _clip_text(
    value: object,
    limit: int = 150,
) -> str:
    clean = " ".join(
        str(value or "").split()
    )
    if len(clean) <= limit:
        return clean
    return clean[: max(1, limit - 1)].rstrip(" ,.;:") + "."


def _gift_reply(
    event: dict[str, Any],
    *,
    display_name: str,
    user_key: str,
) -> str:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    gift_name = str(metadata.get("gift_name") or event.get("text") or "presente").strip()
    count = int(metadata.get("count") or 1)
    return build_gift_reply(
        display_name=display_name,
        gift_name=gift_name,
        gift_count=count,
        user_key=user_key,
        current_game=CURRENT_GAME,
    )


def _comment_reply(
    event: dict[str, Any],
    *,
    display_name: str,
    comment: str,
    user_key: str,
    top_priority: bool,
) -> str:
    if not top_priority:
        return build_main_reply(
            display_name=display_name,
            comment=comment,
            user_key=user_key,
            current_game=CURRENT_GAME,
        )

    event_id = str(event.get("id") or "")
    candidate = build_main_reply(
        display_name=display_name,
        comment=comment,
        user_key=(
            f"{user_key}:top:{event_id}"
        ),
        current_game=CURRENT_GAME,
    )
    if not top_supporters.response_was_recent(
        candidate
    ):
        top_supporters.remember_response(
            candidate
        )
        return candidate

    for suffix in (
        " Vou variar a resposta.",
        " Indo por outro caminho agora.",
        " Sem repetir a fala anterior.",
    ):
        alternative = _clip_text(
            f"{candidate}{suffix}",
            150,
        )
        if not top_supporters.response_was_recent(
            alternative
        ):
            top_supporters.remember_response(
                alternative
            )
            return alternative

    top_supporters.remember_response(
        candidate
    )
    return candidate


def _gift_metadata(
    event: dict[str, Any],
) -> dict[str, Any]:
    metadata = (
        event.get("metadata")
        if isinstance(event.get("metadata"), dict)
        else {}
    )
    return metadata


def _gift_name(
    event: dict[str, Any],
) -> str:
    metadata = _gift_metadata(event)
    return str(
        metadata.get("gift_name")
        or event.get("text")
        or "presente"
    ).strip()


def _gift_key_from_name(
    value: object,
) -> str:
    normalized = (
        unicodedata.normalize(
            "NFKD",
            str(value or ""),
        )
        .encode(
            "ascii",
            "ignore",
        )
        .decode("ascii")
        .lower()
    )
    return (
        re.sub(
            r"[^a-z0-9]+",
            "-",
            normalized,
        ).strip("-")
        or "presente"
    )


def _gift_key(
    event: dict[str, Any],
    song_trigger: dict[str, Any] | None = None,
) -> str:
    if isinstance(song_trigger, dict):
        trigger_key = str(
            song_trigger.get("gift_key")
            or ""
        ).strip()
        if trigger_key:
            return trigger_key

    return _gift_key_from_name(
        _gift_name(event)
    )


def _is_heart_me_band_gift_key(gift_key: str) -> bool:
    return str(gift_key or "").strip().casefold() in HEART_ME_BAND_GIFT_KEYS


def _gift_count(
    event: dict[str, Any],
) -> int:
    metadata = _gift_metadata(event)
    try:
        return max(
            1,
            int(
                metadata.get("count")
                or metadata.get("gift_count")
                or 1
            ),
        )
    except (TypeError, ValueError):
        return 1


def _heart_me_band_user_payload(
    event: dict[str, Any],
    *,
    avatar_path: str,
    display_name: str,
    user_key: str,
    gift_key: str,
) -> dict[str, Any]:
    return {
        "heart_me_band": True,
        "event_id": str(event.get("id") or ""),
        "gift_key": gift_key,
        "gift_name": _gift_name(event),
        "gift_count": _gift_count(event),
        "user_id": str(event.get("user_id") or user_key),
        "username": str(event.get("username") or ""),
        "display_name": display_name,
        "avatar_url": str(event.get("avatar_url") or event.get("profile_image") or ""),
        "avatar_path": avatar_path,
    }


def _heart_me_band_gift_message(
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "heart_me_band_gift",
        "source": "event_decision_worker",
        "time": time.time(),
        "payload": payload,
    }


def _gift_total_coins(
    event: dict[str, Any],
) -> int:
    metadata = _gift_metadata(event)
    try:
        return int(metadata.get("gift_total_coins") or 0)
    except (TypeError, ValueError):
        return 0


def _event_bucket(
    event: dict[str, Any],
    modulo: int,
) -> int:
    if modulo <= 1:
        return 0
    source = (
        str(event.get("id") or "")
        + "|"
        + str(event.get("user_id") or "")
        + "|"
        + str(event.get("text") or "")
    )
    digest = hashlib.sha256(source.encode("utf-8", errors="ignore")).digest()
    return digest[0] % modulo


def _pending_event_counts() -> tuple[int, int]:
    state = live_events.status()
    return (
        int(state.get("comments_pending") or 0),
        int(state.get("gifts_pending") or 0),
    )


async def _flush_top_supporters_update() -> None:
    message = top_supporters.take_update_message()
    if message:
        await godot_bridge.send(message)


def _prune_gift_thank_buffer(
    now: float,
) -> None:
    _GIFT_THANK_BUFFER[:] = [
        item
        for item in _GIFT_THANK_BUFFER
        if now - float(item.get("at") or 0.0)
        <= GIFT_GROUP_THANK_WINDOW_SECONDS
    ]


def _record_gift_for_group(
    event: dict[str, Any],
    *,
    display_name: str,
    user_key: str,
    gift_key: str,
) -> None:
    now = time.time()
    _prune_gift_thank_buffer(now)
    _GIFT_THANK_BUFFER.append(
        {
            "at": now,
            "event_id": str(event.get("id") or ""),
            "display_name": display_name,
            "user_key": user_key,
            "gift_key": gift_key,
        }
    )


def _format_gift_group_names(
    items: list[dict[str, Any]],
) -> str:
    names: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = _clip_text(
            item.get("display_name") or "visitante",
            24,
        )
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)

    if not names:
        return "pessoal"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} e {names[1]}"
    if len(names) <= 4:
        return f"{', '.join(names[:-1])} e {names[-1]}"
    return f"{', '.join(names[:3])} e mais {len(names) - 3} pessoas"


def _gift_group_reply(
    items: list[dict[str, Any]],
) -> str:
    names = _format_gift_group_names(items)
    return _clip_text(
        f"{names}, obrigado pelos presentes.",
        150,
    )


def _gift_group_ready(
    *,
    comments_pending: int,
    gifts_pending: int,
) -> list[dict[str, Any]]:
    now = time.time()
    _prune_gift_thank_buffer(now)
    if len(_GIFT_THANK_BUFFER) >= GIFT_GROUP_THANK_MIN_EVENTS:
        group = list(_GIFT_THANK_BUFFER)
        _GIFT_THANK_BUFFER.clear()
        return group
    if (
        gifts_pending <= 0
        and comments_pending <= 0
        and len(_GIFT_THANK_BUFFER) >= GIFT_GROUP_THANK_FLUSH_MIN_EVENTS
        and all(
            now
            - _LAST_GIFT_THANK_AT_BY_KEY.get(
                str(item.get("gift_key") or ""),
                0.0,
            )
            >= GIFT_INDIVIDUAL_THANK_COOLDOWN_SECONDS
            for item in _GIFT_THANK_BUFFER
        )
    ):
        group = list(_GIFT_THANK_BUFFER)
        _GIFT_THANK_BUFFER.clear()
        return group
    return []


def _should_thank_individual_gift(
    event: dict[str, Any],
    *,
    comments_pending: int,
    gifts_pending: int,
    gift_key: str,
) -> tuple[bool, str]:
    now = time.time()

    if comments_pending > 0:
        return False, "comment_waiting"

    if (
        now - _LAST_GIFT_THANK_AT_BY_KEY.get(gift_key, 0.0)
        < GIFT_INDIVIDUAL_THANK_COOLDOWN_SECONDS
    ):
        return False, "cooldown"

    if _gift_total_coins(event) >= GIFT_HIGH_VALUE_COINS:
        return True, "high_value"

    return True, "selected"


def _gift_job_metadata(
    event: dict[str, Any],
    *,
    avatar_path: str,
    user_key: str,
    display_name: str,
    source: str = "social_gift",
    audio_role: str = "gift_thanks",
    song_trigger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": source,
        "event_id": str(event.get("id") or ""),
        "speaker": "main",
        "user_id": str(event.get("user_id") or user_key),
        "username": str(event.get("username") or ""),
        "display_name": display_name,
        "avatar_url": str(event.get("avatar_url") or event.get("profile_image") or ""),
        "avatar_path": avatar_path,
        "snake_color": _snake_color_for_user(user_key),
        "audio_role": audio_role,
        "gift_key": _gift_key(event, song_trigger),
    }
    if song_trigger is not None:
        metadata["song_trigger"] = song_trigger
    return metadata


def _mark_gift_thanked(
    gift_key: str,
) -> None:
    _LAST_GIFT_THANK_AT_BY_KEY[gift_key] = time.time()


def _mark_gift_group_thanked(
    items: list[dict[str, Any]],
) -> None:
    for item in items:
        gift_key = str(
            item.get("gift_key")
            or ""
        ).strip()
        if gift_key:
            _mark_gift_thanked(gift_key)


async def process_once() -> dict[str, Any]:
    if not godot_bridge.status().get("connected"):
        return {"ok": False, "reason": "godot_disconnected"}

    await _flush_top_supporters_update()

    if not _speech_pipeline_can_accept_next():
        return {"ok": False, "reason": "speech_pipeline_busy"}

    event = live_events.pop_next_event()
    if not event:
        return {"ok": False, "reason": "events_empty"}

    kind = str(event.get("kind") or "").strip().casefold()
    if kind == "comment":
        return await _process_comment(event)
    if kind == "gift":
        return await _process_gift(event)
    if kind == "system":
        return _process_system(event)

    _write_status(last_action="unknown_event", last_error=f"kind={kind}")
    return {"ok": False, "reason": "unknown_event", "event": event}


async def _process_comment(event: dict[str, Any]) -> dict[str, Any]:
    avatar_path = await _send_spectator_activity(event, source="social_comment")
    display_name = _display_name(event)
    comment = str(event.get("text") or "").strip()
    user_key = _event_user_key(event) or display_name
    top_priority = top_supporters.is_priority_comment(event)
    response_text = await asyncio.to_thread(
        _comment_reply,
        event,
        display_name=display_name,
        comment=comment,
        user_key=user_key,
        top_priority=top_priority,
    )

    sequence_id = uuid.uuid4().hex
    common_metadata = {
        "source": "social_comment",
        "event_id": str(event.get("id") or ""),
        "chat_reference_sequence_id": sequence_id,
        "user_id": str(event.get("user_id") or user_key),
        "username": str(event.get("username") or ""),
        "display_name": display_name,
        "avatar_url": str(event.get("avatar_url") or event.get("profile_image") or ""),
        "avatar_path": avatar_path,
        "snake_color": _snake_color_for_user(user_key),
        "audio_role": "chat_reference",
        "top_supporter_priority": top_priority,
        "top_supporter_rank": (
            (
                event.get("metadata")
                if isinstance(event.get("metadata"), dict)
                else {}
            ).get("top_supporter_rank")
            if top_priority
            else 0
        ),
    }

    user_job = enqueue_text(
        comment,
        priority=81 if top_priority else 71,
        actor="user",
        metadata={
            **common_metadata,
            "speaker": "spectator",
            "chat_reference_part": "user",
            "user_avatar_reference": True,
            "blocks_events": True,
        },
    )
    main_job = enqueue_text(
        response_text,
        priority=80 if top_priority else 70,
        actor="main",
        metadata={
            **common_metadata,
            "speaker": "main",
            "chat_reference_part": "response",
            "chat_reference_response": True,
            "paired_user_job_id": str(user_job.get("id") or ""),
        },
    )

    _write_status(
        running=True,
        last_action="comment_dialogue_queued",
        last_error="",
        events_processed=int(_STATE.get("events_processed") or 0) + 1,
        comments_processed=int(_STATE.get("comments_processed") or 0) + 1,
    )
    return {"ok": True, "kind": "comment", "user_job": user_job, "main_job": main_job}


async def _process_gift(event: dict[str, Any]) -> dict[str, Any]:
    incoming_metadata = (
        event.get("metadata")
        if isinstance(event.get("metadata"), dict)
        else {}
    )
    configured_reaction = content_updates.reaction_for_gift_name(
        incoming_metadata.get("gift_name")
        or event.get("text")
        or ""
    )
    configured_action = str(
        (configured_reaction or {}).get("action")
        or ""
    )
    if configured_action == "gift_cannon":
        incoming_metadata["cannon_only"] = True
        event["metadata"] = incoming_metadata

    avatar_path = await _send_spectator_activity(event, source="social_gift")
    await godot_bridge.send(gift_apples_message(event))

    metadata = (
        event.get("metadata")
        if isinstance(event.get("metadata"), dict)
        else {}
    )
    if bool(metadata.get("cannon_only", False)):
        _write_status(
            running=True,
            last_action="gift_cannon_queued",
            last_error="",
            events_processed=int(_STATE.get("events_processed") or 0) + 1,
            gifts_processed=int(_STATE.get("gifts_processed") or 0) + 1,
        )
        return {
            "ok": True,
            "kind": "gift",
            "cannon_only": True,
        }

    display_name = _display_name(event)
    user_key = _event_user_key(event) or display_name
    song_trigger = song_runtime.song_trigger_for_gift_event(
        event
    )
    gift_key = _gift_key(
        event,
        song_trigger,
    )
    heart_me_band = (
        _is_heart_me_band_gift_key(gift_key)
        or configured_action == "heart_me_band"
    )
    heart_me_payload: dict[str, Any] = {}
    if heart_me_band:
        heart_me_payload = _heart_me_band_user_payload(
            event,
            avatar_path=avatar_path,
            display_name=display_name,
            user_key=user_key,
            gift_key=gift_key,
        )
        await godot_bridge.send(
            _heart_me_band_gift_message(
                heart_me_payload
            )
        )

        if song_runtime.singing_active():
            _write_status(
                running=True,
                last_action="heart_me_band_user_joined_active_song",
                last_error="",
                events_processed=int(_STATE.get("events_processed") or 0) + 1,
                gifts_processed=int(_STATE.get("gifts_processed") or 0) + 1,
            )
            return {
                "ok": True,
                "kind": "gift",
                "heart_me_band": heart_me_payload,
                "thanked": False,
            }

    song = song_trigger.get(
        "song"
    )

    if isinstance(song, dict):
        message = song_runtime.song_ready_message(
            song.get(
                "id",
                "",
            )
        )
        payload = (
            message.get("payload")
            if isinstance(
                message.get("payload"),
                dict,
            )
            else {}
        )
        metadata = (
            event.get("metadata")
            if isinstance(
                event.get("metadata"),
                dict,
            )
            else {}
        )
        payload["gift_event_id"] = str(
            event.get("id")
            or ""
        )
        payload["gift_name"] = str(
            metadata.get("gift_name")
            or event.get("text")
            or ""
        )
        payload["gift_count"] = int(
            metadata.get("count")
            or 1
        )
        payload["gift_key"] = gift_key
        payload["display_name"] = display_name
        payload["user_id"] = str(
            event.get("user_id")
            or user_key
        )
        payload["username"] = str(
            event.get("username")
            or ""
        )
        payload["avatar_url"] = str(
            event.get("avatar_url")
            or event.get("profile_image")
            or ""
        )
        payload["avatar_path"] = avatar_path

        if heart_me_band:
            payload["heart_me_band"] = True
            payload["mix_path"] = ""
            payload["vocal_volume"] = 1.0
            payload["instrumental_volume"] = 0.86
            payload["mix_volume"] = 0.0
            payload["fanclub_users"] = [
                heart_me_payload,
            ]

        message["payload"] = payload

        sent = await godot_bridge.send(
            message
        )

        if sent:
            song_runtime.mark_playing(
                payload.get(
                    "song_id",
                    "",
                ),
                payload.get(
                    "title",
                    "",
                ),
                duration=payload.get(
                    "timeline_end",
                    0.0,
                ),
            )
            reply = await asyncio.to_thread(
                _gift_reply,
                event,
                display_name=display_name,
                user_key=user_key,
            )
            job = enqueue_text(
                reply,
                priority=int(event.get("priority") or 65),
                actor="main",
                metadata=_gift_job_metadata(
                    event,
                    avatar_path=avatar_path,
                    user_key=user_key,
                    display_name=display_name,
                    source="social_gift_song",
                    audio_role="gift_song_thanks",
                    song_trigger=song_trigger,
                ),
            )
            _GIFT_THANK_BUFFER.clear()
            _mark_gift_thanked(gift_key)
            _write_status(
                running=True,
                last_action="gift_song_sent_thanks_queued",
                last_error="",
                events_processed=int(_STATE.get("events_processed") or 0) + 1,
                gifts_processed=int(_STATE.get("gifts_processed") or 0) + 1,
            )
            return {
                "ok": True,
                "kind": "gift",
                "song": payload,
                "song_trigger": song_trigger,
                "job": job,
                "thanked": True,
            }

    _record_gift_for_group(
        event,
        display_name=display_name,
        user_key=user_key,
        gift_key=gift_key,
    )
    comments_pending, gifts_pending = _pending_event_counts()
    group_items = _gift_group_ready(
        comments_pending=comments_pending,
        gifts_pending=gifts_pending,
    )

    if group_items:
        reply = _gift_group_reply(
            group_items
        )
        job = enqueue_text(
            reply,
            priority=int(event.get("priority") or 65),
            actor="main",
            metadata=_gift_job_metadata(
                event,
                avatar_path=avatar_path,
                user_key=user_key,
                display_name=display_name,
                source="social_gift_group",
                audio_role="gift_group_thanks",
                song_trigger=song_trigger,
            ),
        )
        _mark_gift_group_thanked(group_items)
        _write_status(
            running=True,
            last_action="gift_group_thanks_queued",
            last_error="",
            events_processed=int(_STATE.get("events_processed") or 0) + 1,
            gifts_processed=int(_STATE.get("gifts_processed") or 0) + 1,
        )
        return {
            "ok": True,
            "kind": "gift",
            "song_trigger": song_trigger,
            "job": job,
            "grouped": True,
        }

    should_thank, skip_reason = _should_thank_individual_gift(
        event,
        comments_pending=comments_pending,
        gifts_pending=gifts_pending,
        gift_key=gift_key,
    )

    if not should_thank:
        _write_status(
            running=True,
            last_action=f"gift_thanks_skipped_{skip_reason}",
            last_error="",
            events_processed=int(_STATE.get("events_processed") or 0) + 1,
            gifts_processed=int(_STATE.get("gifts_processed") or 0) + 1,
        )
        return {
            "ok": True,
            "kind": "gift",
            "song_trigger": song_trigger,
            "thanked": False,
            "reason": skip_reason,
        }

    reply = await asyncio.to_thread(
        _gift_reply,
        event,
        display_name=display_name,
        user_key=user_key,
    )
    job = enqueue_text(
        reply,
        priority=int(event.get("priority") or 65),
        actor="main",
        metadata=_gift_job_metadata(
            event,
            avatar_path=avatar_path,
            user_key=user_key,
            display_name=display_name,
            song_trigger=(
                song_trigger
                if bool(song_trigger.get("mapped"))
                else None
            ),
        ),
    )
    _GIFT_THANK_BUFFER.clear()
    _mark_gift_thanked(gift_key)

    _write_status(
        running=True,
        last_action="gift_thanks_queued",
        last_error="",
        events_processed=int(_STATE.get("events_processed") or 0) + 1,
        gifts_processed=int(_STATE.get("gifts_processed") or 0) + 1,
    )
    return {
        "ok": True,
        "kind": "gift",
        "song_trigger": song_trigger,
        "job": job,
        "thanked": True,
    }


def _process_system(event: dict[str, Any]) -> dict[str, Any]:
    text = str(event.get("text") or "").strip()
    if not text:
        return {"ok": False, "reason": "system_text_empty"}

    job = enqueue_text(
        text,
        priority=int(event.get("priority") or 25),
        actor="main",
        metadata={
            "source": "system",
            "event_id": str(event.get("id") or ""),
            "speaker": "main",
            "audio_role": "system",
        },
    )
    _write_status(
        running=True,
        last_action="system_queued",
        last_error="",
        events_processed=int(_STATE.get("events_processed") or 0) + 1,
    )
    return {"ok": True, "kind": "system", "job": job}
