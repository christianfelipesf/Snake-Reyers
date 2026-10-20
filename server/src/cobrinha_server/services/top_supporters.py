from __future__ import annotations

import re
import threading
import time
import unicodedata
from typing import Any

from cobrinha_server.core.json_store import read_json, write_json_atomic
from cobrinha_server.core.settings import RUNS_DIR


TOP_SUPPORTERS_FILE = RUNS_DIR / "top_supporters_live.json"

TOP_LIMIT = 6
# O ranking vale pela sessao inteira. O estado e limpo ao iniciar/parar a live.
INACTIVE_AFTER_SECONDS = 24.0 * 60.0 * 60.0
LIKE_POINTS = 20
SHARE_POINTS = 40
GIFT_POINTS_PER_COIN = 100
MIN_GIFT_POINTS = 100
NORMAL_CHAT_BEFORE_TOP_PRIORITY = 3
RECENT_RESPONSE_LIMIT = 24

_LOCK = threading.Lock()

_GIFT_COIN_FALLBACK = {
    "rose": 1,
    "rosa": 1,
    "tiktok": 1,
    "ice-cream-cone": 1,
    "ice-cream": 1,
    "doughnut": 30,
    "donut": 30,
    "rosquinha": 30,
}


def _empty_state() -> dict[str, Any]:
    return {
        "users": {},
        "policy": {
            "normal_comments_since_top": 0,
            "last_priority_user_key": "",
            "recent_response_signatures": [],
        },
        "dirty": True,
        "started_at": time.time(),
        "updated_at": time.time(),
    }


def _read_state() -> dict[str, Any]:
    payload = read_json(TOP_SUPPORTERS_FILE, {})
    if not isinstance(payload, dict):
        payload = {}

    users = payload.get("users")
    policy = payload.get("policy")
    if not isinstance(users, dict):
        users = {}
    if not isinstance(policy, dict):
        policy = {}

    return {
        "users": users,
        "policy": {
            "normal_comments_since_top":
                int(policy.get("normal_comments_since_top") or 0),
            "last_priority_user_key":
                str(policy.get("last_priority_user_key") or ""),
            "recent_response_signatures":
                (
                    policy.get("recent_response_signatures")
                    if isinstance(
                        policy.get("recent_response_signatures"),
                        list,
                    )
                    else []
                ),
        },
        "dirty": bool(payload.get("dirty", False)),
        "started_at": float(payload.get("started_at") or 0.0),
        "updated_at": float(payload.get("updated_at") or 0.0),
    }


def _write_state(state: dict[str, Any]) -> None:
    state["updated_at"] = time.time()
    write_json_atomic(TOP_SUPPORTERS_FILE, state)


def reset() -> dict[str, Any]:
    state = _empty_state()
    with _LOCK:
        _write_state(state)
    return status()


def _nested(
    payload: dict[str, Any],
    path: str,
) -> Any:
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _first(
    payload: dict[str, Any],
    *paths: str,
) -> Any:
    for path in paths:
        value = _nested(payload, path)
        if value not in {None, ""}:
            return value
    return None


def _safe_int(
    value: object,
    default: int = 0,
) -> int:
    try:
        return int(float(value if value is not None else default))
    except (TypeError, ValueError):
        return int(default)


def _clean_text(
    value: object,
) -> str:
    return " ".join(str(value or "").strip().split())


def _slug(
    value: object,
) -> str:
    normalized = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def _user_key(
    payload: dict[str, Any],
) -> str:
    for value in (
        payload.get("user_id"),
        payload.get("uniqueId"),
        payload.get("username"),
        payload.get("display_name"),
        payload.get("nickname"),
        _first(payload, "user.userId", "user.uniqueId", "user.nickname"),
    ):
        clean = _clean_text(value).casefold()
        if clean:
            return clean
    return ""


def _display_name(
    payload: dict[str, Any],
) -> str:
    return (
        _clean_text(
            payload.get("display_name")
            or payload.get("nickname")
            or _first(payload, "user.nickname", "user.uniqueId")
            or payload.get("username")
        )
        or "visitante"
    )


def _username(
    payload: dict[str, Any],
) -> str:
    return _clean_text(
        payload.get("username")
        or payload.get("uniqueId")
        or _first(payload, "user.uniqueId")
    )


def _avatar_url(
    payload: dict[str, Any],
) -> str:
    return _clean_text(
        payload.get("avatar_url")
        or payload.get("profile_image")
        or _first(
            payload,
            "profilePictureUrl",
            "user.profilePictureUrl",
            "user.avatarThumb.urlList.0",
        )
    )


def _avatar_path(
    payload: dict[str, Any],
) -> str:
    return _clean_text(
        payload.get("avatar_path")
    )


def _points_breakdown(
    user: dict[str, Any],
) -> dict[str, int]:
    breakdown = user.get("breakdown")
    if not isinstance(breakdown, dict):
        breakdown = {}
    return {
        "likes": int(breakdown.get("likes") or 0),
        "shares": int(breakdown.get("shares") or 0),
        "gift_coins": int(breakdown.get("gift_coins") or 0),
        "gift_points": int(breakdown.get("gift_points") or 0),
    }


def _record_activity(
    payload: dict[str, Any],
    *,
    points: int,
    likes: int = 0,
    shares: int = 0,
    gift_coins: int = 0,
    gift_points: int = 0,
) -> dict[str, Any]:
    key = _user_key(payload)
    if not key:
        return {
            "ok": False,
            "ignored": True,
            "reason": "user_empty",
        }

    now = time.time()
    points = max(0, int(points))

    with _LOCK:
        state = _read_state()
        users = dict(state.get("users") or {})
        user = (
            dict(users.get(key))
            if isinstance(users.get(key), dict)
            else {}
        )
        breakdown = _points_breakdown(user)
        breakdown["likes"] += max(0, int(likes))
        breakdown["shares"] += max(0, int(shares))
        breakdown["gift_coins"] += max(0, int(gift_coins))
        breakdown["gift_points"] += max(0, int(gift_points))
        display_name = _display_name(payload)
        if display_name.casefold() == "visitante":
            display_name = str(
                user.get("display_name")
                or display_name
            )
        avatar_url = (
            _avatar_url(payload)
            or str(user.get("avatar_url") or "")
        )
        avatar_path = (
            _avatar_path(payload)
            or str(user.get("avatar_path") or "")
        )

        user.update(
            {
                "user_key": key,
                "user_id": _clean_text(payload.get("user_id")) or key,
                "username": _username(payload)
                    or str(user.get("username") or ""),
                "display_name": display_name,
                "avatar_url": avatar_url,
                "avatar_path": avatar_path,
                "points": int(user.get("points") or 0) + points,
                "last_interaction_at": now,
                "breakdown": breakdown,
            }
        )

        users[key] = user
        state["users"] = users
        state["dirty"] = True
        _write_state(state)

    return {
        "ok": True,
        "user_key": key,
        "points_added": points,
        "total_points": int(user.get("points") or 0),
        "top": public_entries(),
    }


def _count_from_payload(
    payload: dict[str, Any],
    *paths: str,
) -> int:
    return max(
        1,
        _safe_int(
            _first(payload, *paths),
            1,
        ),
    )


def record_like(
    payload: dict[str, Any],
) -> dict[str, Any]:
    count = _count_from_payload(
        payload,
        "count",
        "likeCount",
        "like_count",
        "likes",
    )
    return _record_activity(
        payload,
        points=count * LIKE_POINTS,
        likes=count,
    )


def record_share(
    payload: dict[str, Any],
) -> dict[str, Any]:
    count = _count_from_payload(
        payload,
        "count",
        "shareCount",
        "share_count",
    )
    return _record_activity(
        payload,
        points=count * SHARE_POINTS,
        shares=count,
    )


def _fallback_gift_coins(
    gift_name: object,
) -> int:
    key = _slug(gift_name)
    if key in _GIFT_COIN_FALLBACK:
        return _GIFT_COIN_FALLBACK[key]
    return 1


def record_gift(
    event: dict[str, Any],
) -> dict[str, Any]:
    metadata = (
        event.get("metadata")
        if isinstance(event.get("metadata"), dict)
        else {}
    )
    count = max(
        1,
        _safe_int(metadata.get("count"), 1),
    )
    coins = _safe_int(
        metadata.get("gift_total_coins"),
        0,
    )
    if coins <= 0:
        coin_value = _safe_int(
            metadata.get("gift_coin_value"),
            0,
        )
        coins = coin_value * count
    if coins <= 0:
        coins = (
            _fallback_gift_coins(
                metadata.get("gift_name")
                or event.get("text")
            )
            * count
        )

    gift_points = max(
        MIN_GIFT_POINTS,
        coins * GIFT_POINTS_PER_COIN,
    )
    return _record_activity(
        event,
        points=gift_points,
        gift_coins=coins,
        gift_points=gift_points,
    )


def _active_entries_from_state(
    state: dict[str, Any],
    *,
    now: float | None = None,
) -> list[dict[str, Any]]:
    if now is None:
        now = time.time()

    entries: list[dict[str, Any]] = []
    users = state.get("users")
    if not isinstance(users, dict):
        return []

    for key, raw_user in users.items():
        if not isinstance(raw_user, dict):
            continue
        last_interaction_at = float(
            raw_user.get("last_interaction_at")
            or 0.0
        )
        if (
            last_interaction_at <= 0.0
            or now - last_interaction_at > INACTIVE_AFTER_SECONDS
        ):
            continue
        points = int(raw_user.get("points") or 0)
        if points <= 0:
            continue
        entries.append(
            {
                "user_key": str(
                    raw_user.get("user_key")
                    or key
                ),
                "user_id": str(
                    raw_user.get("user_id")
                    or key
                ),
                "username": str(
                    raw_user.get("username")
                    or ""
                ),
                "display_name": str(
                    raw_user.get("display_name")
                    or raw_user.get("username")
                    or "visitante"
                ),
                "name": str(
                    raw_user.get("display_name")
                    or raw_user.get("username")
                    or "visitante"
                ),
                "avatar_url": str(
                    raw_user.get("avatar_url")
                    or ""
                ),
                "avatar_path": str(
                    raw_user.get("avatar_path")
                    or ""
                ),
                "points": points,
                "last_interaction_at": last_interaction_at,
                "breakdown": _points_breakdown(raw_user),
            }
        )

    return sorted(
        entries,
        key=lambda item: (
            -int(item.get("points") or 0),
            -float(item.get("last_interaction_at") or 0.0),
            str(item.get("display_name") or ""),
        ),
    )[:TOP_LIMIT]


def public_entries() -> list[dict[str, Any]]:
    with _LOCK:
        state = _read_state()
    return _active_entries_from_state(state)


def active_user_keys() -> set[str]:
    return {
        str(item.get("user_key") or "").casefold()
        for item in public_entries()
        if str(item.get("user_key") or "").strip()
    }


def websocket_message() -> dict[str, Any]:
    return {
        "type": "top_supporters_update",
        "source": "top_supporters",
        "payload": {
            "entries": public_entries(),
            "inactive_after_seconds": INACTIVE_AFTER_SECONDS,
        },
    }


def take_update_message(
    *,
    force: bool = False,
) -> dict[str, Any] | None:
    with _LOCK:
        state = _read_state()
        if not force and not bool(state.get("dirty")):
            return None
        state["dirty"] = False
        _write_state(state)

    return websocket_message()


def _comment_user_key(
    event: dict[str, Any],
) -> str:
    return _user_key(event)


def choose_comment(
    comments: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not comments:
        return None, []

    with _LOCK:
        state = _read_state()
        policy = (
            state.get("policy")
            if isinstance(state.get("policy"), dict)
            else {}
        )
        top_entries = _active_entries_from_state(state)
        top_ranks = {
            str(item.get("user_key") or "").casefold(): index
            for index, item in enumerate(top_entries)
            if str(item.get("user_key") or "").strip()
        }
        top_keys = set(top_ranks)
        normal_since = max(
            0,
            int(policy.get("normal_comments_since_top") or 0),
        )
        last_top_key = str(
            policy.get("last_priority_user_key")
            or ""
        ).casefold()

        indexed = list(enumerate(comments))
        normal_candidates = [
            (index, event)
            for index, event in indexed
            if _comment_user_key(event).casefold()
            not in top_keys
        ]
        top_candidates = [
            (index, event)
            for index, event in indexed
            if _comment_user_key(event).casefold()
            in top_keys
            and _comment_user_key(event).casefold()
            != last_top_key
        ]

        selected_index = 0
        selected_as_top = False
        selected_rank = 0

        if (
            normal_since >= NORMAL_CHAT_BEFORE_TOP_PRIORITY
            and top_candidates
        ):
            selected_index, _event = min(
                top_candidates,
                key=lambda item: (
                    top_ranks.get(
                        _comment_user_key(item[1]).casefold(),
                        TOP_LIMIT,
                    ),
                    float(item[1].get("created_at") or 0.0),
                ),
            )
            selected_as_top = True
            selected_rank = top_ranks.get(
                _comment_user_key(comments[selected_index]).casefold(),
                0,
            )
        elif normal_candidates:
            selected_index = normal_candidates[0][0]

        selected = dict(comments[selected_index])
        selected_key = _comment_user_key(selected).casefold()
        selected_top = selected_key in top_keys

        if selected_as_top:
            metadata = (
                dict(selected.get("metadata"))
                if isinstance(selected.get("metadata"), dict)
                else {}
            )
            metadata["top_supporter_priority"] = True
            metadata["top_supporter_rank"] = selected_rank + 1
            selected["metadata"] = metadata
            selected["priority"] = max(
                int(selected.get("priority") or 0),
                76,
            )
            policy["normal_comments_since_top"] = 0
            policy["last_priority_user_key"] = selected_key
        elif not selected_top:
            policy["normal_comments_since_top"] = min(
                NORMAL_CHAT_BEFORE_TOP_PRIORITY,
                normal_since + 1,
            )

        state["policy"] = policy
        _write_state(state)

    remaining = [
        dict(event)
        for index, event in enumerate(comments)
        if index != selected_index
    ]
    return selected, remaining


def is_priority_comment(
    event: dict[str, Any],
) -> bool:
    metadata = (
        event.get("metadata")
        if isinstance(event.get("metadata"), dict)
        else {}
    )
    return bool(metadata.get("top_supporter_priority"))


def _response_signature(
    text: object,
) -> str:
    clean = re.sub(
        r"\s+",
        " ",
        str(text or "").casefold(),
    ).strip()
    return clean


def response_was_recent(
    text: object,
) -> bool:
    signature = _response_signature(text)
    if not signature:
        return False
    with _LOCK:
        state = _read_state()
        policy = state.get("policy")
        recent = (
            policy.get("recent_response_signatures")
            if isinstance(policy, dict)
            and isinstance(
                policy.get("recent_response_signatures"),
                list,
            )
            else []
        )
    return signature in recent


def remember_response(
    text: object,
) -> None:
    signature = _response_signature(text)
    if not signature:
        return
    with _LOCK:
        state = _read_state()
        policy = (
            state.get("policy")
            if isinstance(state.get("policy"), dict)
            else {}
        )
        recent = [
            str(item)
            for item in list(
                policy.get("recent_response_signatures")
                or []
            )
            if str(item)
        ]
        recent = [
            item
            for item in recent
            if item != signature
        ]
        recent.append(signature)
        policy["recent_response_signatures"] = (
            recent[-RECENT_RESPONSE_LIMIT:]
        )
        state["policy"] = policy
        _write_state(state)


def status() -> dict[str, Any]:
    with _LOCK:
        state = _read_state()
        entries = _active_entries_from_state(state)
        users = state.get("users")
        user_count = (
            len(users)
            if isinstance(users, dict)
            else 0
        )

    return {
        "active": bool(entries),
        "entries": entries,
        "user_count": user_count,
        "top_limit": TOP_LIMIT,
        "inactive_after_seconds": INACTIVE_AFTER_SECONDS,
        "like_points": LIKE_POINTS,
        "share_points": SHARE_POINTS,
        "gift_points_per_coin": GIFT_POINTS_PER_COIN,
        "normal_chat_before_top_priority":
            NORMAL_CHAT_BEFORE_TOP_PRIORITY,
        "updated_at": float(state.get("updated_at") or 0.0),
    }
