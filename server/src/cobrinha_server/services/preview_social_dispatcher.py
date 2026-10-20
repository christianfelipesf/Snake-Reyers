from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from cobrinha_server.bridge.godot_bridge import (
    preview_bridge,
)
from cobrinha_server.services import (
    live_events,
    song_runtime,
)
from cobrinha_server.services.avatar_cache import (
    cache_profile_avatar,
)
from cobrinha_server.services.chat_safety import (
    comment_is_eligible,
)
from cobrinha_server.services.social_events import (
    spectator_user_message,
)
from cobrinha_server.services.social_reply import (
    build_main_reply,
)
from cobrinha_server.services.social_dispatcher import (
    gift_apples_message,
)
from cobrinha_server.services.tts_service import (
    prepare_tts_input,
    synthesize_for_job,
)


_TASK: asyncio.Task[None] | None = None

_STATE: dict[str, Any] = {
    "running": False,
    "task_alive": False,
    "comments_dispatched": 0,
    "comments_ignored": 0,
    "gifts_dispatched": 0,
    "spectator_speeches": 0,
    "main_speeches": 0,
    "last_action": "",
    "last_error": "",
    "last_event_id": "",
    "updated_at": 0.0,
}


def _update(
    **values: Any,
) -> None:
    _STATE.update(values)
    _STATE["updated_at"] = time.time()


def status() -> dict[str, Any]:
    return {
        **_STATE,
        "task_alive": bool(
            _TASK
            and not _TASK.done()
        ),
    }


def start_preview_social_dispatcher() -> dict[str, Any]:
    global _TASK

    if (
        _TASK is not None
        and not _TASK.done()
    ):
        return status()

    _TASK = asyncio.create_task(
        _loop(),
        name=(
            "cobrinha-preview-social-dispatcher"
        ),
    )

    _update(
        running=True,
        last_action="started",
        last_error="",
    )

    return status()


async def _loop() -> None:
    try:
        while True:
            await dispatch_once()
            await asyncio.sleep(0.20)

    except asyncio.CancelledError:
        raise

    finally:
        _update(
            running=False,
        )


def _speech_message(
    *,
    text: str,
    speech: dict[str, Any],
    speaker: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    timeline = (
        speech.get("timeline")
        if isinstance(
            speech.get("timeline"),
            dict,
        )
        else {}
    )

    return {
        "type": "speech_ready",
        "source": "preview_social",
        "time": time.time(),
        "payload": {
            "job_id": (
                "preview-social-"
                + uuid.uuid4().hex
            ),
            "text": prepare_tts_input(
                text
            ),
            "audio_path": str(
                speech.get("audio_path")
                or ""
            ),
            "segments": timeline.get(
                "segments",
                [],
            ),
            "timeline_end": float(
                timeline.get(
                    "timeline_end",
                    0.0,
                )
                or 0.0
            ),
            "speech_end": float(
                timeline.get(
                    "speech_end",
                    0.0,
                )
                or 0.0
            ),
            "trailing_mute_at": float(
                timeline.get(
                    "trailing_mute_at",
                    0.0,
                )
                or 0.0
            ),
            "metadata": {
                "preview": True,
                "source":
                    "preview_social",
                "speaker": speaker,
                "event_id": str(
                    event.get("id")
                    or ""
                ),
                "user_id": str(
                    event.get("user_id")
                    or ""
                ),
                "username": str(
                    event.get("username")
                    or ""
                ),
                "display_name": str(
                    event.get("display_name")
                    or ""
                ),
            },
        },
    }


async def _send_speech_and_wait(
    *,
    text: str,
    speaker: str,
    event: dict[str, Any],
) -> bool:
    speech = await asyncio.to_thread(
        synthesize_for_job,
        text,
    )

    message = _speech_message(
        text=text,
        speech=speech,
        speaker=speaker,
        event=event,
    )

    sent = await preview_bridge.send(
        message
    )

    if not sent:
        return False

    timeline = (
        speech.get("timeline")
        if isinstance(
            speech.get("timeline"),
            dict,
        )
        else {}
    )

    duration = max(
        0.20,
        float(
            timeline.get(
                "timeline_end",
                0.0,
            )
            or 0.0
        ),
    )

    await asyncio.sleep(
        duration + 0.35
    )

    return True


async def _send_spectator_activity(
    event: dict[str, Any],
    *,
    source: str,
) -> bool:
    avatar_path = ""

    avatar_url = str(
        event.get("avatar_url")
        or event.get("profile_image")
        or ""
    ).strip()

    if avatar_url:
        avatar_result = (
            await asyncio.to_thread(
                cache_profile_avatar,
                avatar_url,
                user_key=str(
                    event.get("user_id")
                    or event.get("username")
                    or "preview"
                ),
            )
        )

        if avatar_result.get("ok"):
            avatar_path = str(
                avatar_result.get("path")
                or ""
            )

    metadata = (
        event.get("metadata")
        if isinstance(event.get("metadata"), dict)
        else {}
    )

    user_message = spectator_user_message(
        {
            "user_id":
                event.get("user_id"),
            "username":
                event.get("username"),
            "display_name":
                event.get("display_name"),
            "avatar_url":
                event.get("avatar_url"),
            "comment": (
                event.get("text")
                or metadata.get("gift_name")
                or ""
            ),
        },
        avatar_path=avatar_path,
        source=source,
        preview=True,
    )

    payload = user_message.setdefault(
        "payload",
        {},
    )

    if isinstance(payload, dict):
        payload["slot_limit"] = 16
        payload["activity_kind"] = str(
            event.get("kind")
            or ""
        )

    user_message["time"] = time.time()

    return bool(
        await preview_bridge.send(
            user_message
        )
    )


async def dispatch_comment(
    event: dict[str, Any],
) -> dict[str, Any]:
    comment = str(
        event.get("text")
        or ""
    ).strip()

    if not comment_is_eligible(
        comment
    ):
        _update(
            comments_ignored=(
                int(
                    _STATE.get(
                        "comments_ignored"
                    )
                    or 0
                )
                + 1
            ),
            last_action=
                "ignored_comment",
            last_event_id=str(
                event.get("id")
                or ""
            ),
        )

        return {
            "ok": False,
            "ignored": True,
            "reason":
                "comment_not_eligible",
        }

    avatar_path = ""

    avatar_url = str(
        event.get("avatar_url")
        or event.get("profile_image")
        or ""
    ).strip()

    if avatar_url:
        avatar_result = (
            await asyncio.to_thread(
                cache_profile_avatar,
                avatar_url,
                user_key=str(
                    event.get("user_id")
                    or event.get("username")
                    or "preview"
                ),
            )
        )

        if avatar_result.get("ok"):
            avatar_path = str(
                avatar_result.get("path")
                or ""
            )

    user_message = spectator_user_message(
        {
            "user_id":
                event.get("user_id"),
            "username":
                event.get("username"),
            "display_name":
                event.get("display_name"),
            "avatar_url":
                event.get("avatar_url"),
            "comment":
                comment,
        },
        avatar_path=avatar_path,
        source="preview_social",
        preview=True,
    )

    user_message["time"] = time.time()

    if not await preview_bridge.send(
        user_message
    ):
        return {
            "ok": False,
            "reason":
                "preview_user_not_sent",
        }

    spectator_sent = (
        await _send_speech_and_wait(
            text=comment,
            speaker="spectator",
            event=event,
        )
    )

    if not spectator_sent:
        return {
            "ok": False,
            "reason":
                "spectator_speech_not_sent",
        }

    display_name = str(
        event.get("display_name")
        or event.get("username")
        or "visitante"
    ).strip()

    response_text = await asyncio.to_thread(
        build_main_reply,
        display_name=display_name,
        comment=comment,
        user_key=(
            str(
                event.get("username")
                or display_name
            )
        ),
    )

    main_sent = (
        await _send_speech_and_wait(
            text=response_text,
            speaker="main",
            event=event,
        )
    )

    if not main_sent:
        return {
            "ok": False,
            "reason":
                "main_speech_not_sent",
        }

    _update(
        comments_dispatched=(
            int(
                _STATE.get(
                    "comments_dispatched"
                )
                or 0
            )
            + 1
        ),
        spectator_speeches=(
            int(
                _STATE.get(
                    "spectator_speeches"
                )
                or 0
            )
            + 1
        ),
        main_speeches=(
            int(
                _STATE.get(
                    "main_speeches"
                )
                or 0
            )
            + 1
        ),
        last_action=
            "comment_dialogue_finished",
        last_error="",
        last_event_id=str(
            event.get("id")
            or ""
        ),
    )

    return {
        "ok": True,
        "response_text":
            response_text,
    }


async def dispatch_gift(
    event: dict[str, Any],
) -> dict[str, Any]:
    await _send_spectator_activity(
        event,
        source="preview_social_gift",
    )

    message = gift_apples_message(
        event
    )

    message["source"] = (
        "preview_social_gift"
    )

    if isinstance(
        message.get("payload"),
        dict,
    ):
        message["payload"].setdefault(
            "metadata",
            {},
        )

    sent = await preview_bridge.send(
        message
    )

    song_trigger = song_runtime.song_trigger_for_gift_event(
        event,
        consume=False,
    )
    song = song_trigger.get(
        "song"
    )

    song_sent = False

    if isinstance(song, dict):
        song_message = song_runtime.song_ready_message(
            song.get(
                "id",
                "",
            )
        )
        song_message["source"] = (
            "preview_social_gift"
        )
        song_sent = bool(
            await preview_bridge.send(
                song_message
            )
        )

    if sent:
        _update(
            gifts_dispatched=(
                int(
                    _STATE.get(
                        "gifts_dispatched"
                    )
                    or 0
                )
                + 1
            ),
            last_action=
                "gift_apples_sent",
            last_error="",
            last_event_id=str(
                event.get("id")
                or ""
            ),
        )

    return {
        "ok": bool(sent),
        "sent": bool(sent),
        "song_sent": song_sent,
    }


async def dispatch_once() -> dict[str, Any]:
    if not preview_bridge.status().get(
        "connected"
    ):
        return {
            "ok": False,
            "reason":
                "preview_disconnected",
        }

    event_state = live_events.status()

    if int(
        event_state.get(
            "preview_comments_pending"
        )
        or 0
    ) > 0:
        comment = (
            live_events
            .pop_next_preview_comment()
        )

        if comment is not None:
            try:
                return await dispatch_comment(
                    comment
                )
            except Exception as exc:
                _update(
                    last_action=
                        "comment_error",
                    last_error=(
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                    last_event_id=str(
                        comment.get("id")
                        or ""
                    ),
                )

                return {
                    "ok": False,
                    "reason":
                        "comment_exception",
                }

    if int(
        event_state.get(
            "preview_gifts_pending"
        )
        or 0
    ) > 0:
        gift = (
            live_events
            .pop_next_preview_gift()
        )

        if gift is not None:
            try:
                return await dispatch_gift(
                    gift
                )
            except Exception as exc:
                _update(
                    last_action=
                        "gift_error",
                    last_error=(
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                    last_event_id=str(
                        gift.get("id")
                        or ""
                    ),
                )

                return {
                    "ok": False,
                    "reason":
                        "gift_exception",
                }

    return {
        "ok": False,
        "reason":
            "preview_events_empty",
    }
