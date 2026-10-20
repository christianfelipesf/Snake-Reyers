from __future__ import annotations

import math
import threading
import time
import uuid
from typing import Any

from cobrinha_server.core.json_store import (
    read_json,
    write_json_atomic,
)
from cobrinha_server.core.settings import RUNS_DIR
from cobrinha_server.services.social_events import (
    normalize_social_user,
)
from cobrinha_server.services import top_supporters
from cobrinha_server.services.chat_safety import (
    comment_is_eligible,
)


SOCIAL_EVENTS_FILE = (
    RUNS_DIR
    / "social_live_events.json"
)

SOCIAL_EVENTS_LIMIT = 100
COMMENT_DUPLICATE_WINDOW_SECONDS = 600.0
GIFT_DUPLICATE_WINDOW_SECONDS = 900.0
GIFT_SIGNATURE_DUPLICATE_WINDOW_SECONDS = 0.5
COMMENT_MAX_AGE_SECONDS = 45.0
GIFT_MAX_AGE_SECONDS = 300.0
SYSTEM_MAX_AGE_SECONDS = 180.0
COMMENT_BACKLOG_LIMIT = 3
GIFT_QUEUE_MAX_EVENTS = 12
MAX_CONSECUTIVE_GIFTS_WITH_COMMENT_WAITING = 2
COMMENT_FORCE_AFTER_SECONDS = 0.75
GIFT_FORCE_AFTER_SECONDS = 1.5
GIFT_BASE_PRIORITY = 90
HIGH_VALUE_GIFT_COIN_VALUE = 30
HIGH_VALUE_GIFT_PRIORITY = 130
GIFT_CANNON_PRIORITY = 150

INTERRUPTIBLE_SYSTEM_SOURCES = {
    "tiktok_member",
    "welcome",
}

_LOCK = threading.Lock()
_gift_burst_count = 0


def _event_created_at(event: dict[str, Any]) -> float:
    try:
        return float(event.get("created_at") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _prune_events(
    events: list[dict[str, Any]],
    *,
    max_age: float,
) -> list[dict[str, Any]]:
    now = time.time()
    keep: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        created_at = _event_created_at(event)
        if created_at <= 0.0 or now - created_at <= max_age:
            keep.append(dict(event))
    return keep


def _read_state() -> dict[str, Any]:
    payload = read_json(
        SOCIAL_EVENTS_FILE,
        {},
    )

    if not isinstance(payload, dict):
        payload = {}

    comments = payload.get("comments")
    gifts = payload.get("gifts")
    system = payload.get("system")

    return {
        "comments":
            comments
            if isinstance(comments, list)
            else [],
        "gifts":
            gifts
            if isinstance(gifts, list)
            else [],
        "system":
            system
            if isinstance(system, list)
            else [],
        "last_event":
            payload.get("last_event")
            if isinstance(
                payload.get("last_event"),
                dict,
            )
            else {},
        "comment_dedup":
            payload.get("comment_dedup")
            if isinstance(
                payload.get("comment_dedup"),
                dict,
            )
            else {},
        "gift_dedup":
            payload.get("gift_dedup")
            if isinstance(
                payload.get("gift_dedup"),
                dict,
            )
            else {},
        "updated_at": float(
            payload.get("updated_at")
            or 0.0
        ),
    }


def _write_state(
    state: dict[str, Any],
) -> None:
    state["comments"] = _prune_events(
        list(
            state.get("comments")
            or []
        ),
        max_age=COMMENT_MAX_AGE_SECONDS,
    )[-SOCIAL_EVENTS_LIMIT:]

    state["gifts"] = _prune_events(
        list(
            state.get("gifts")
            or []
        ),
        max_age=GIFT_MAX_AGE_SECONDS,
    )[-GIFT_QUEUE_MAX_EVENTS:]

    state["system"] = _prune_events(
        list(
            state.get("system")
            or []
        ),
        max_age=SYSTEM_MAX_AGE_SECONDS,
    )[-SOCIAL_EVENTS_LIMIT:]

    state["gift_dedup"] = _prune_gift_dedup(
        dict(state.get("gift_dedup") or {}),
        time.time(),
    )

    state["updated_at"] = (
        time.time()
    )

    write_json_atomic(
        SOCIAL_EVENTS_FILE,
        state,
    )


def reset() -> None:
    with _LOCK:
        _write_state(
            {
                "comments": [],
                "gifts": [],
                "system": [],
                "last_event": {},
                "comment_dedup": {},
                "gift_dedup": {},
                "updated_at":
                    time.time(),
            }
        )


def _nested(
    payload: dict[str, Any],
    path: str,
) -> Any:
    current: Any = payload

    for part in path.split("."):
        if not isinstance(
            current,
            dict,
        ):
            return None

        current = current.get(part)

    return current


def _first(
    payload: dict[str, Any],
    *paths: str,
) -> Any:
    for path in paths:
        value = _nested(
            payload,
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


def gift_count(
    payload: dict[str, Any],
) -> int:
    value = _first(
        payload,
        "count",
        "repeatCount",
        "repeat_count",
        "gift.repeatCount",
        "gift.repeat_count",
        "giftDetails.repeatCount",
    )

    return max(
        1,
        _safe_int(
            value,
            1,
        ),
    )


def gift_coin_value(
    payload: dict[str, Any],
) -> int:
    value = _first(
        payload,
        "coin_value",
        "diamondCount",
        "diamond_count",
        "gift.diamondCount",
        "gift.diamond_count",
        "giftDetails.diamondCount",
        "giftDetails.diamond_count",
        "giftDetails.diamonds",
        "gift.diamonds",
    )

    return max(
        0,
        _safe_int(
            value,
            0,
        ),
    )


def gift_total_coins(
    payload: dict[str, Any],
) -> int:
    explicit_total = _first(
        payload,
        "gift_total_coins",
        "total_coins",
        "totalCoins",
    )

    if explicit_total is not None:
        return max(
            0,
            _safe_int(
                explicit_total,
                0,
            ),
        )

    return (
        gift_coin_value(payload)
        * gift_count(payload)
    )


def apples_for_gift(
    total_coins: int,
) -> int:
    coins = max(
        0,
        int(total_coins),
    )

    if coins <= 0:
        return 1

    # Escala conservadora para a arena:
    # presentes pequenos geram 1 maca;
    # presentes maiores geram progressivamente mais,
    # com limite para impedir inundacao instantanea.
    if coins < 10:
        return 1

    if coins < 50:
        return 2

    if coins < 200:
        return 3

    if coins < 500:
        return 4

    if coins < 1000:
        return 5

    return min(
        12,
        5
        + int(
            math.ceil(
                (
                    coins
                    - 1000
                )
                / 1000.0
            )
        ),
    )


def _comment_user_key(
    payload: dict[str, Any],
    user: dict[str, Any],
) -> str:
    for candidate in (
        user.get("user_id"),
        user.get("username"),
        user.get("display_name"),
        payload.get("user_id"),
        payload.get("username"),
    ):
        value = str(
            candidate
            or ""
        ).strip().casefold()

        if value:
            return value

    return ""


def _comment_text_signature(
    text: object,
) -> str:
    return " ".join(
        str(
            text
            or ""
        )
        .casefold()
        .split()
    )


def _prune_comment_dedup(
    history: dict[str, Any],
    now: float,
) -> dict[str, Any]:
    keep: dict[str, Any] = {}

    for key, item in history.items():
        if not isinstance(
            item,
            dict,
        ):
            continue

        try:
            created_at = float(
                item.get("created_at")
                or 0.0
            )
        except (
            TypeError,
            ValueError,
        ):
            created_at = 0.0

        if (
            created_at > 0.0
            and now - created_at
            <= COMMENT_DUPLICATE_WINDOW_SECONDS
        ):
            keep[str(key)] = item

    return keep


def _prune_gift_dedup(
    history: dict[str, Any],
    now: float,
) -> dict[str, Any]:
    keep: dict[str, Any] = {}
    for key, item in history.items():
        if not isinstance(item, dict):
            continue
        try:
            created_at = float(item.get("created_at") or 0.0)
        except (TypeError, ValueError):
            created_at = 0.0
        if created_at > 0.0 and now - created_at <= GIFT_DUPLICATE_WINDOW_SECONDS:
            keep[str(key)] = dict(item)
    return keep


def _gift_dedup_key(
    payload: dict[str, Any],
    user: dict[str, Any],
    gift_name: str,
    count: int,
    total_coins: int,
) -> tuple[str, bool]:
    upstream_id = str(
        _first(
            payload,
            "event_id",
            "eventId",
            "msg_id",
            "msgId",
            "message_id",
            "messageId",
        )
        or ""
    ).strip()
    if upstream_id and upstream_id != "0":
        return "id:" + upstream_id, True

    user_key = str(
        user.get("user_id")
        or user.get("username")
        or user.get("display_name")
        or ""
    ).strip().casefold()
    signature = "|".join(
        (
            user_key,
            gift_name.strip().casefold(),
            str(count),
            str(total_coins),
        )
    )
    return "signature:" + signature, False


def _drop_interruptible_system_backlog(
    state: dict[str, Any],
) -> None:
    system = []
    for event in list(state.get("system") or []):
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        source = str(metadata.get("source") or event.get("source") or "").strip().casefold()
        if source in INTERRUPTIBLE_SYSTEM_SOURCES:
            continue
        system.append(event)
    state["system"] = system


def push_comment(
    payload: dict[str, Any],
) -> dict[str, Any]:
    user = normalize_social_user(
        payload
    )

    now = time.time()
    comment = str(
        user.get("comment")
        or ""
    ).strip()

    if not comment_is_eligible(comment):
        return {
            "id": uuid.uuid4().hex,
            "kind": "comment",
            "ignored": True,
            "reason": "comment_not_eligible",
            "user_id": user["user_id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "profile_image": user["avatar_url"],
            "avatar_url": user["avatar_url"],
            "text": comment,
            "created_at": now,
        }

    event = {
        "id": uuid.uuid4().hex,
        "kind": "comment",
        "priority": 70,
        "user_id":
            user["user_id"],
        "username":
            user["username"],
        "display_name":
            user["display_name"],
        "profile_image":
            user["avatar_url"],
        "avatar_url":
            user["avatar_url"],
        "text":
            comment,
        "created_at":
            now,
        "metadata": {
            "source":
                str(
                    payload.get(
                        "source"
                    )
                    or "tiktok"
                ),
        },
    }

    user_key = _comment_user_key(
        payload,
        user,
    )

    signature = (
        _comment_text_signature(
            comment
        )
    )

    with _LOCK:
        state = _read_state()

        history = _prune_comment_dedup(
            dict(
                state.get(
                    "comment_dedup"
                )
                or {}
            ),
            now,
        )

        previous = (
            history.get(user_key)
            if user_key
            else None
        )

        if (
            isinstance(
                previous,
                dict,
            )
            and signature
            and str(
                previous.get(
                    "signature"
                )
                or ""
            ) == signature
        ):
            history[user_key] = {
                "signature":
                    signature,
                "text":
                    comment,
                "created_at":
                    now,
            }

            state["comment_dedup"] = (
                history
            )

            _write_state(state)

            return {
                **event,
                "ignored": True,
                "reason":
                    "duplicate_comment",
            }

        if (
            user_key
            and signature
        ):
            history[user_key] = {
                "signature":
                    signature,
                "text":
                    comment,
                "created_at":
                    now,
            }

        state["comment_dedup"] = (
            history
        )

        _drop_interruptible_system_backlog(state)

        user_event_key = _comment_user_key(
            payload,
            user,
        )
        comments = [
            item
            for item in list(state["comments"])
            if (
                not isinstance(item, dict)
                or _comment_user_key(item, normalize_social_user(item))
                != user_event_key
            )
        ]
        comments.append(event)
        state["comments"] = comments

        state["last_event"] = event
        _write_state(state)

    return event


def push_gift(
    payload: dict[str, Any],
) -> dict[str, Any]:
    user = normalize_social_user(
        payload
    )

    gift_name = str(
        _first(
            payload,
            "gift_name",
            "giftName",
            "gift.name",
            "giftDetails.giftName",
            "giftDetails.name",
        )
        or "presente"
    ).strip()

    count = gift_count(
        payload
    )

    coin_value = gift_coin_value(
        payload
    )

    total_coins = gift_total_coins(
        payload
    )

    apples = apples_for_gift(
        total_coins
    )

    dedup_key, has_upstream_id = _gift_dedup_key(
        payload,
        user,
        gift_name,
        count,
        total_coins,
    )

    event = {
        "id": uuid.uuid4().hex,
        "kind": "gift",
        "priority":
            (
                GIFT_CANNON_PRIORITY
                if bool(payload.get("cannon_only", False))
                else (
                    HIGH_VALUE_GIFT_PRIORITY
                    if coin_value >= HIGH_VALUE_GIFT_COIN_VALUE
                    else GIFT_BASE_PRIORITY + min(30, apples)
                )
            ),
        "user_id":
            user["user_id"],
        "username":
            user["username"],
        "display_name":
            user["display_name"],
        "profile_image":
            user["avatar_url"],
        "avatar_url":
            user["avatar_url"],
        "text": gift_name,
        "created_at":
            time.time(),
        "metadata": {
            "source":
                str(
                    payload.get(
                        "source"
                    )
                    or "tiktok"
                ),
            "gift_name":
                gift_name,
            "count":
                count,
            "gift_coin_value":
                coin_value,
            "gift_total_coins":
                total_coins,
            "apple_count":
                apples,
            "high_value_gift":
                coin_value >= HIGH_VALUE_GIFT_COIN_VALUE,
            "upstream_event_id": str(
                payload.get("event_id")
                or payload.get("eventId")
                or ""
            ),
            "combo_id": str(payload.get("combo_id") or ""),
            "gift_id": str(payload.get("gift_id") or ""),
            "gift_type": _safe_int(payload.get("gift_type"), 0),
            "repeat_end": bool(payload.get("repeat_end", False)),
            "cannon_only": bool(payload.get("cannon_only", False)),
            "suppress_gift_cannon": bool(
                payload.get("suppress_gift_cannon", False)
            ),
        },
    }

    with _LOCK:
        state = _read_state()
        now = time.time()
        gift_history = _prune_gift_dedup(
            dict(state.get("gift_dedup") or {}),
            now,
        )
        previous = gift_history.get(dedup_key)
        previous_at = 0.0
        if isinstance(previous, dict):
            try:
                previous_at = float(previous.get("created_at") or 0.0)
            except (TypeError, ValueError):
                previous_at = 0.0

        duplicate_window = (
            GIFT_DUPLICATE_WINDOW_SECONDS
            if has_upstream_id
            else GIFT_SIGNATURE_DUPLICATE_WINDOW_SECONDS
        )
        if previous_at > 0.0 and now - previous_at <= duplicate_window:
            state["gift_dedup"] = gift_history
            _write_state(state)
            return {
                **event,
                "ignored": True,
                "reason": "duplicate_gift",
                "duplicate_of": str(previous.get("event_id") or ""),
            }

        gift_history[dedup_key] = {
            "event_id": str(event.get("id") or ""),
            "created_at": now,
        }
        state["gift_dedup"] = gift_history
        _drop_interruptible_system_backlog(state)
        gifts = list(
            state["gifts"]
        )
        gifts.append(event)
        state["gifts"] = gifts

        state["last_event"] = event
        _write_state(state)

    return event


def _event_priority(event: dict[str, Any]) -> int:
    try:
        return int(event.get("priority") or 0)
    except (TypeError, ValueError):
        return 0


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            dict(event)
            for event in events
            if isinstance(event, dict)
        ],
        key=lambda item: (
            -_event_priority(item),
            _event_created_at(item),
        ),
    )


def _should_pop_comment_before_gift(
    comments: list[dict[str, Any]],
    gifts: list[dict[str, Any]],
) -> bool:
    if not comments:
        return False

    if not gifts:
        return True

    top_comment_priority = _event_priority(
        comments[0]
    )
    top_gift_priority = _event_priority(
        gifts[0]
    )

    if _gift_burst_count >= MAX_CONSECUTIVE_GIFTS_WITH_COMMENT_WAITING:
        return True

    if top_gift_priority > top_comment_priority:
        return False

    oldest_gift_at = min(
        [
            _event_created_at(gift)
            for gift in gifts
            if _event_created_at(gift) > 0.0
        ]
        or [0.0]
    )

    if (
        oldest_gift_at > 0.0
        and time.time() - oldest_gift_at >= GIFT_FORCE_AFTER_SECONDS
    ):
        return False

    oldest_comment_at = min(
        [
            _event_created_at(comment)
            for comment in comments
            if _event_created_at(comment) > 0.0
        ]
        or [0.0]
    )

    if (
        oldest_comment_at > 0.0
        and time.time() - oldest_comment_at >= COMMENT_FORCE_AFTER_SECONDS
    ):
        return True

    return top_comment_priority >= top_gift_priority


def has_pending_reactions() -> bool:
    with _LOCK:
        state = _read_state()
        return bool(
            state["comments"]
            or state["gifts"]
            or state.get("system")
        )


def pop_next_event() -> dict[str, Any] | None:
    global _gift_burst_count

    with _LOCK:
        state = _read_state()
        state["comments"] = _prune_events(
            list(
                state.get("comments")
                or []
            ),
            max_age=COMMENT_MAX_AGE_SECONDS,
        )
        state["gifts"] = _prune_events(
            list(
                state.get("gifts")
                or []
            ),
            max_age=GIFT_MAX_AGE_SECONDS,
        )
        state["system"] = _prune_events(
            list(
                state.get("system")
                or []
            ),
            max_age=SYSTEM_MAX_AGE_SECONDS,
        )
        comments = _sort_events(
            state.get("comments")
            or []
        )[:COMMENT_BACKLOG_LIMIT]
        gifts = _sort_events(
            state.get("gifts")
            or []
        )
        system = _sort_events(
            state.get("system")
            or []
        )

        event: dict[str, Any] | None = None

        if _should_pop_comment_before_gift(
            comments,
            gifts,
        ):
            event, comments = top_supporters.choose_comment(
                comments
            )
            _gift_burst_count = 0
        elif gifts:
            event = gifts.pop(0)
            _gift_burst_count += 1
        elif comments:
            event, comments = top_supporters.choose_comment(
                comments
            )
            _gift_burst_count = 0
        elif system:
            event = system.pop(0)
            _gift_burst_count = 0

        if event is None:
            state["comments"] = comments
            state["gifts"] = gifts
            state["system"] = system
            _write_state(state)
            return None

        state["comments"] = comments
        state["gifts"] = gifts
        state["system"] = system
        state["last_dispatched_event"] = event
        _write_state(state)
        return event


def push_system_event(
    text: str,
    *,
    source: str = "system",
    priority: int = 25,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean = " ".join(
        str(text or "").strip().split()
    )
    if not clean:
        raise ValueError("system_event_empty")

    event = {
        "id": uuid.uuid4().hex,
        "kind": "system",
        "priority": int(priority),
        "text": clean,
        "created_at": time.time(),
        "metadata": {
            **dict(metadata or {}),
            "source": str(source or "system").strip() or "system",
        },
    }

    with _LOCK:
        state = _read_state()
        system = list(
            state.get("system")
            or []
        )
        system.append(event)
        state["system"] = system
        state["last_event"] = event
        _write_state(state)

    return event


def drop_system_events_by_source(
    source: str,
) -> int:
    clean_source = str(source or "").strip().casefold()
    if not clean_source:
        return 0

    with _LOCK:
        state = _read_state()
        before = len(
            state.get("system")
            or []
        )
        keep = []
        for event in list(state.get("system") or []):
            if not isinstance(event, dict):
                continue
            metadata = event.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            event_source = str(
                metadata.get("source")
                or event.get("source")
                or ""
            ).strip().casefold()
            if event_source != clean_source:
                keep.append(event)
        state["system"] = keep
        _write_state(state)

    return before - len(keep)


def pop_next_comment() -> (
    dict[str, Any]
    | None
):
    with _LOCK:
        state = _read_state()

        comments = list(
            state["comments"]
        )

        if not comments:
            return None

        event = comments.pop(0)
        state["comments"] = comments
        _write_state(state)

    return event


def pop_next_gift() -> (
    dict[str, Any]
    | None
):
    with _LOCK:
        state = _read_state()

        gifts = list(
            state["gifts"]
        )

        if not gifts:
            return None

        event = gifts.pop(0)
        state["gifts"] = gifts
        _write_state(state)

    return event


def status() -> dict[str, Any]:
    with _LOCK:
        state = _read_state()

    return {
        "comments_pending":
            len(
                state["comments"]
            ),
        "gifts_pending":
            len(
                state["gifts"]
            ),
        "system_pending":
            len(
                state.get(
                    "system"
                )
                or []
            ),
        "last_event":
            state["last_event"],
        "last_dispatched_event":
            state.get(
                "last_dispatched_event",
                {},
            ),
        "updated_at":
            state["updated_at"],
        "comment_dedup_size":
            len(
                state.get(
                    "comment_dedup"
                )
                or {}
            ),
        "gift_dedup_size":
            len(
                state.get(
                    "gift_dedup"
                )
                or {}
            ),
        "comments":
            state["comments"][-10:],
        "gifts":
            state["gifts"][-10:],
        "system":
            (
                state.get("system")
                or []
            )[-10:],
    }
