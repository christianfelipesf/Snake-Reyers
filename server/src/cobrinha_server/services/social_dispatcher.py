from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from cobrinha_server.bridge.godot_bridge import (
    godot_bridge,
)
from cobrinha_server.services import live_events
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
from cobrinha_server.services.speech_queue import (
    enqueue_text,
)


_TASK: asyncio.Task[None] | None = None

_STATE: dict[str, Any] = {
    "running": False,
    "last_action": "",
    "last_error": "",
    "comments_dispatched": 0,
    "comments_ignored": 0,
    "gifts_dispatched": 0,
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


def start_social_dispatcher() -> dict[str, Any]:
    global _TASK

    if (
        _TASK is not None
        and not _TASK.done()
    ):
        return status()

    _TASK = asyncio.create_task(
        _loop(),
        name="cobrinha-social-dispatcher",
    )

    _update(
        running=True,
        last_action="started",
        last_error="",
    )

    return status()


async def stop_social_dispatcher() -> dict[str, Any]:
    global _TASK

    task = _TASK

    if task is not None:
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

    _TASK = None

    _update(
        running=False,
        last_action="stopped",
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


def enqueue_comment_dialogue(
    event: dict[str, Any],
) -> dict[str, Any]:
    comment = str(
        event.get("text")
        or ""
    ).strip()

    if not comment_is_eligible(
        comment
    ):
        return {
            "ok": False,
            "ignored": True,
            "reason": "comment_not_eligible",
        }

    display_name = str(
        event.get("display_name")
        or event.get("username")
        or "visitante"
    ).strip()

    username = str(
        event.get("username")
        or ""
    ).strip()

    sequence_id = uuid.uuid4().hex

    response_text = build_main_reply(
        display_name=display_name,
        comment=comment,
        user_key=(
            username
            or display_name
        ),
    )

    common_metadata = {
        "source": "social_comment",
        "social_sequence_id":
            sequence_id,
        "event_id":
            str(
                event.get("id")
                or ""
            ),
        "user_id":
            str(
                event.get("user_id")
                or username
            ),
        "username":
            username,
        "display_name":
            display_name,
    }

    user_job = enqueue_text(
        comment,
        priority=61,
        metadata={
            **common_metadata,
            "speaker": "spectator",
            "social_part": "user",
            "blocks_social": True,
        },
    )

    main_job = enqueue_text(
        response_text,
        priority=60,
        metadata={
            **common_metadata,
            "speaker": "main",
            "social_part": "response",
            "paired_user_job_id":
                user_job["id"],
        },
    )

    return {
        "ok": True,
        "sequence_id": sequence_id,
        "user_job": user_job,
        "main_job": main_job,
        "response_text":
            response_text,
    }


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
            last_action="ignored_comment",
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
        or event.get(
            "profile_image"
        )
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
                    or ""
                ),
            )
        )

        if avatar_result.get("ok"):
            avatar_path = str(
                avatar_result.get("path")
                or ""
            )

    message = spectator_user_message(
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
                event.get("text"),
        },
        avatar_path=avatar_path,
        source="social_comment",
    )

    try:
        sent = await godot_bridge.send(
            message
        )
    except Exception as exc:
        _update(
            last_action=
                "social_user_send_error",
            last_error=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return {
            "ok": False,
            "reason":
                "social_user_send_error",
        }

    if not sent:
        return {
            "ok": False,
            "reason":
                "social_user_not_sent",
        }

    queued = enqueue_comment_dialogue(
        event
    )

    if queued.get("ok"):
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
            last_action=
                "comment_dialogue_queued",
            last_error="",
        )

    return queued


def gift_apples_message(
    event: dict[str, Any],
) -> dict[str, Any]:
    metadata = (
        event.get("metadata")
        if isinstance(
            event.get("metadata"),
            dict,
        )
        else {}
    )

    apple_count = max(
        1,
        min(
            12,
            int(
                metadata.get(
                    "apple_count"
                )
                or 1
            ),
        ),
    )

    cannon_only = bool(metadata.get("cannon_only", False))

    return {
        "type": "gift_cannon" if cannon_only else "gift_apples",
        "source": "social_gift",
        "time": time.time(),
        "payload": {
            "event_id":
                str(
                    event.get("id")
                    or ""
                ),
            "upstream_event_id":
                str(
                    metadata.get("upstream_event_id")
                    or ""
                ),
            "combo_id":
                str(
                    metadata.get("combo_id")
                    or ""
                ),
            "user_id":
                str(
                    event.get("user_id")
                    or event.get(
                        "username"
                    )
                    or ""
                ),
            "display_name":
                str(
                    event.get(
                        "display_name"
                    )
                    or event.get(
                        "username"
                    )
                    or ""
                ),
            "gift_name":
                str(
                    metadata.get(
                        "gift_name"
                    )
                    or event.get("text")
                    or ""
                ),
            "gift_total_coins":
                int(
                    metadata.get(
                        "gift_total_coins"
                    )
                    or 0
                ),
            "gift_count":
                int(metadata.get("count") or 1),
            "gift_type":
                int(metadata.get("gift_type") or 0),
            "repeat_end":
                bool(metadata.get("repeat_end", False)),
            "cannon_only": cannon_only,
            "suppress_gift_cannon":
                bool(metadata.get("suppress_gift_cannon", False)),
            "apple_count":
                apple_count,
        },
    }


async def dispatch_gift(
    event: dict[str, Any],
) -> dict[str, Any]:
    message = gift_apples_message(
        event
    )

    try:
        sent = await godot_bridge.send(
            message
        )
    except Exception as exc:
        _update(
            last_action="gift_send_error",
            last_error=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return {
            "ok": False,
            "reason":
                "gift_send_error",
        }

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
        )

    return {
        "ok": bool(sent),
        "sent": bool(sent),
        "message": message,
    }


async def dispatch_once() -> dict[str, Any]:
    if not godot_bridge.status().get(
        "connected"
    ):
        return {
            "ok": False,
            "reason":
                "godot_disconnected",
        }

    event_state = live_events.status()

    if int(
        event_state.get(
            "comments_pending"
        )
        or 0
    ) > 0:
        comment = (
            live_events.pop_next_comment()
        )

        if comment is not None:
            return await dispatch_comment(
                comment
            )

    if int(
        event_state.get(
            "gifts_pending"
        )
        or 0
    ) > 0:
        gift = (
            live_events.pop_next_gift()
        )

        if gift is not None:
            return await dispatch_gift(
                gift
            )

    return {
        "ok": False,
        "reason": "events_empty",
    }
