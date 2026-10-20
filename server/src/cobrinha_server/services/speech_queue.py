from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

from cobrinha_server.core.json_store import read_json, write_json_atomic
from cobrinha_server.core.settings import RUNS_DIR
from cobrinha_server.models import MicroSegment
from cobrinha_server.services import spectator_voices
from cobrinha_server.services.tts_service import safe_tts_chunks, synthesize_for_job


PENDING_QUEUE_FILE = RUNS_DIR / "speech_pending_queue.json"
READY_QUEUE_FILE = RUNS_DIR / "speech_ready_queue.json"
READY_PAIR_QUEUE_FILE = RUNS_DIR / "speech_ready_pair_queue.json"
PAIR_PLAYBACK_FILE = RUNS_DIR / "speech_pair_playback.json"
ACTIVE_SPEECH_FILE = RUNS_DIR / "speech_active.json"
MANUAL_SEQUENCE_FILE = RUNS_DIR / "speech_manual_sequence.json"
RESET_STATE_FILE = RUNS_DIR / "speech_reset_state.json"

PENDING_JOB_MAX_AGE_SECONDS = 120.0
READY_JOB_MAX_AGE_SECONDS = 90.0
PAIR_JOB_MAX_AGE_SECONDS = 120.0
ACTIVE_JOB_STALE_GRACE_SECONDS = 45.0
ACTIVE_JOB_MIN_MAX_AGE_SECONDS = 120.0
MANUAL_SEQUENCE_MAX_CHARS = 150
MANUAL_SEQUENCE_PREFETCH = 2
MANUAL_SEQUENCE_ORPHAN_TIMEOUT_SECONDS = 180.0

_LOCK = threading.RLock()


def _now() -> float:
    return time.time()


def _read_list(path: Path) -> list[dict[str, Any]]:
    raw = read_json(path, [])
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _read_dict(path: Path) -> dict[str, Any]:
    raw = read_json(path, {})
    if not isinstance(raw, dict):
        return {}
    return dict(raw)


def _job_metadata(job: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(job, dict):
        return {}
    metadata = job.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    return dict(metadata)


def _job_created_at(job: dict[str, Any]) -> float:
    metadata = _job_metadata(job)
    for value in (job.get("created_at"), metadata.get("created_at"), metadata.get("event_created_at")):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0.0:
            return number
    return 0.0


def _last_reset_at() -> float:
    payload = _read_dict(RESET_STATE_FILE)
    try:
        return float(payload.get("reset_at") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _job_survives_reset(job: dict[str, Any]) -> bool:
    reset_at = _last_reset_at()
    if reset_at <= 0.0:
        return True

    created_at = _job_created_at(job)
    return created_at > 0.0 and created_at >= reset_at


def _drop_jobs_before_reset(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reset_at = _last_reset_at()
    if reset_at <= 0.0:
        return jobs
    return [
        job
        for job in jobs
        if _job_created_at(job) > 0.0 and _job_created_at(job) >= reset_at
    ]


def _sort_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(jobs, key=lambda item: (-int(item.get("priority") or 0), _job_created_at(item)))


def _prune_old_jobs(jobs: list[dict[str, Any]], *, max_age: float) -> list[dict[str, Any]]:
    now = _now()
    keep: list[dict[str, Any]] = []
    for job in jobs:
        created_at = _job_created_at(job)
        if created_at <= 0.0 or now - created_at <= max_age:
            keep.append(job)
    return keep


def _chat_reference_sequence_id(job: dict[str, Any]) -> str:
    metadata = _job_metadata(job)
    return str(metadata.get("chat_reference_sequence_id") or metadata.get("social_sequence_id") or "").strip()


def _chat_reference_part(job: dict[str, Any]) -> str:
    metadata = _job_metadata(job)
    part = str(metadata.get("chat_reference_part") or metadata.get("social_part") or "").strip().casefold()
    if part in {"user", "avatar", "spectator"}:
        return "user"
    if part in {"response", "main"}:
        return "response"
    if metadata.get("chat_reference_response"):
        return "response"
    if metadata.get("user_avatar_reference"):
        return "user"
    return ""


def _is_chat_reference_pair_job(job: dict[str, Any]) -> bool:
    return bool(_chat_reference_sequence_id(job) and _chat_reference_part(job))


def _read_pair_queue() -> dict[str, Any]:
    raw = _read_dict(READY_PAIR_QUEUE_FILE)
    pairs = raw.get("pairs")
    order = raw.get("order")
    if not isinstance(pairs, dict):
        pairs = {}
    if not isinstance(order, list):
        order = []
    return {
        "pairs": {str(key): dict(value) for key, value in pairs.items() if isinstance(value, dict)},
        "order": [str(item) for item in order if str(item or "").strip()],
        "updated_at": float(raw.get("updated_at") or 0.0),
    }


def _write_pair_queue(state: dict[str, Any]) -> None:
    state["updated_at"] = _now()
    write_json_atomic(READY_PAIR_QUEUE_FILE, state)


def _active_pair_playback() -> dict[str, Any]:
    return _read_dict(PAIR_PLAYBACK_FILE)


def _write_pair_playback(payload: dict[str, Any]) -> None:
    write_json_atomic(PAIR_PLAYBACK_FILE, payload)


def _find_pair_companion_part(
    queue: list[dict[str, Any]],
    *,
    sequence_id: str,
    wanted_part: str,
) -> int:
    for index, job in enumerate(queue):
        if _chat_reference_sequence_id(job) != sequence_id:
            continue
        if _chat_reference_part(job) == wanted_part:
            return index
    return -1


def reset_speech_queues() -> None:
    with _LOCK:
        reset_at = _now()
        write_json_atomic(PENDING_QUEUE_FILE, [])
        write_json_atomic(READY_QUEUE_FILE, [])
        write_json_atomic(READY_PAIR_QUEUE_FILE, {"pairs": {}, "order": []})
        write_json_atomic(PAIR_PLAYBACK_FILE, {})
        write_json_atomic(ACTIVE_SPEECH_FILE, {})
        write_json_atomic(MANUAL_SEQUENCE_FILE, {"active": False, "reset_at": reset_at})
        write_json_atomic(RESET_STATE_FILE, {"reset_at": reset_at})


def enqueue_text(
    text: str,
    *,
    priority: int = 40,
    metadata: dict[str, Any] | None = None,
    actor: str = "main",
) -> dict[str, Any]:
    clean = str(text or "").strip()
    if not clean:
        raise ValueError("Texto vazio.")

    now = _now()
    prepared_metadata = {**dict(metadata or {}), "created_at": now}
    job = {
        "id": uuid.uuid4().hex,
        "text": clean,
        "actor": str(actor or "main").strip() or "main",
        "priority": int(priority),
        "metadata": prepared_metadata,
        "created_at": now,
    }

    with _LOCK:
        queue = _prune_old_jobs(_read_list(PENDING_QUEUE_FILE), max_age=PENDING_JOB_MAX_AGE_SECONDS)
        queue.append(job)
        write_json_atomic(PENDING_QUEUE_FILE, _sort_jobs(queue)[:100])

    return dict(job)


def enqueue_manual_sequence(text: str, *, priority: int = 90) -> dict[str, Any]:
    parts = safe_tts_chunks(
        text,
        max_chars=MANUAL_SEQUENCE_MAX_CHARS,
    )
    parts = [
        str(part).strip()
        for part in parts
        if str(part or "").strip()
    ]
    if not parts:
        raise ValueError("Texto manual vazio.")

    current = _read_manual_sequence()
    if bool(current.get("active")):
        raise RuntimeError("Ja existe uma fala manual em andamento.")

    now = _now()
    state: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "active": True,
        "priority": int(priority),
        "chunks": parts,
        "next_enqueue_index": 0,
        "last_finished_index": -1,
        "created_at": now,
        "updated_at": now,
    }

    write_json_atomic(MANUAL_SEQUENCE_FILE, state)
    _fill_manual_sequence_window(state)
    write_json_atomic(MANUAL_SEQUENCE_FILE, state)
    return _public_manual_sequence(state)


def manual_sequence_status() -> dict[str, Any]:
    return _public_manual_sequence(_read_manual_sequence())


def _read_manual_sequence() -> dict[str, Any]:
    payload = read_json(MANUAL_SEQUENCE_FILE, {"active": False})
    return payload if isinstance(payload, dict) else {"active": False}


def _manual_sequence_age_reference(state: dict[str, Any]) -> float:
    for key in ("updated_at", "created_at"):
        try:
            value = float(state.get(key) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0.0:
            return value
    return 0.0


def _manual_sequence_is_orphaned(
    state: dict[str, Any],
    *,
    pending: list[dict[str, Any]],
    ready: list[dict[str, Any]],
    active: dict[str, Any] | None,
) -> bool:
    if not bool(state.get("active")):
        return False

    sequence_id = str(state.get("id") or "").strip()
    if not sequence_id:
        return True

    if active is not None and _manual_job_matches(active, sequence_id):
        return False

    for job in [*pending, *ready]:
        if _manual_job_matches(job, sequence_id):
            return False

    reference = _manual_sequence_age_reference(state)
    if reference <= 0.0:
        return False

    return _now() - reference > MANUAL_SEQUENCE_ORPHAN_TIMEOUT_SECONDS


def _expire_manual_sequence_if_orphaned(
    state: dict[str, Any],
    *,
    pending: list[dict[str, Any]],
    ready: list[dict[str, Any]],
    active: dict[str, Any] | None,
) -> dict[str, Any]:
    if not _manual_sequence_is_orphaned(
        state,
        pending=pending,
        ready=ready,
        active=active,
    ):
        return state

    state = dict(state)
    state["active"] = False
    state["aborted_at"] = _now()
    state["abort_reason"] = "orphaned_manual_sequence"
    state["updated_at"] = _now()
    write_json_atomic(MANUAL_SEQUENCE_FILE, state)
    return state


def _public_manual_sequence(state: dict[str, Any]) -> dict[str, Any]:
    chunks = state.get("chunks")
    chunks = chunks if isinstance(chunks, list) else []
    return {
        "id": str(state.get("id") or ""),
        "active": bool(state.get("active")),
        "chunk_count": len(chunks),
        "next_enqueue_index": int(state.get("next_enqueue_index") or 0),
        "last_finished_index": int(
            state.get("last_finished_index")
            if state.get("last_finished_index") is not None
            else -1
        ),
        "created_at": float(state.get("created_at") or 0.0),
        "updated_at": float(state.get("updated_at") or 0.0),
        "completed_at": float(state.get("completed_at") or 0.0),
    }


def _manual_job_matches(job: dict[str, Any], sequence_id: str) -> bool:
    metadata = _job_metadata(job)
    return (
        str(metadata.get("source") or "") == "manual"
        and str(metadata.get("manual_sequence_id") or "") == sequence_id
    )


def _fill_manual_sequence_window(state: dict[str, Any]) -> None:
    chunks = state.get("chunks")
    chunks = chunks if isinstance(chunks, list) else []

    if not chunks or not bool(state.get("active")):
        return

    last_finished = int(
        state.get("last_finished_index")
        if state.get("last_finished_index") is not None
        else -1
    )
    next_index = int(state.get("next_enqueue_index") or 0)

    target_exclusive = min(
        len(chunks),
        last_finished + 1 + MANUAL_SEQUENCE_PREFETCH,
    )

    while next_index < target_exclusive:
        enqueue_text(
            str(chunks[next_index]),
            priority=int(state.get("priority") or 90),
            actor="main",
            metadata={
                "source": "manual",
                "manual_sequence_id": str(state.get("id") or ""),
                "manual_sequence_index": next_index,
                "manual_sequence_part": next_index + 1,
                "manual_sequence_total": len(chunks),
                "manual_sequence_last": next_index == len(chunks) - 1,
                "blocks_events": True,
                "speaker": "main",
            },
        )
        next_index += 1
        state["next_enqueue_index"] = next_index
        state["updated_at"] = _now()


def pop_pending() -> dict[str, Any] | None:
    with _LOCK:
        queue = _sort_jobs(
            _drop_jobs_before_reset(
                _prune_old_jobs(
                    _read_list(PENDING_QUEUE_FILE),
                    max_age=PENDING_JOB_MAX_AGE_SECONDS,
                )
            )
        )
        if not queue:
            write_json_atomic(PENDING_QUEUE_FILE, [])
            return None

        manual_sequence = _read_manual_sequence()
        if bool(manual_sequence.get("active")):
            sequence_id = str(manual_sequence.get("id") or "")
            matches = [
                (index, job)
                for index, job in enumerate(queue)
                if isinstance(job, dict)
                and _manual_job_matches(job, sequence_id)
            ]
            if not matches:
                manual_sequence = _expire_manual_sequence_if_orphaned(
                    manual_sequence,
                    pending=queue,
                    ready=_read_list(READY_QUEUE_FILE),
                    active=active_job(),
                )
                if bool(manual_sequence.get("active")):
                    return None
                selected_index = 0
                job = queue[selected_index]
            else:
                selected_index, job = min(
                    matches,
                    key=lambda pair: int(
                        _job_metadata(pair[1]).get("manual_sequence_index")
                        or 0
                    ),
                )

        else:
            pair_state = _read_pair_queue()
            pairs = pair_state.get("pairs", {})
            selected_index = 0
            for sequence_id, pair in pairs.items():
                if not isinstance(pair, dict):
                    continue
                if pair.get("user") and not pair.get("response"):
                    companion_index = _find_pair_companion_part(queue, sequence_id=sequence_id, wanted_part="response")
                elif pair.get("response") and not pair.get("user"):
                    companion_index = _find_pair_companion_part(queue, sequence_id=sequence_id, wanted_part="user")
                else:
                    companion_index = -1
                if companion_index >= 0:
                    selected_index = companion_index
                    break

            job = queue[selected_index]

        queue.pop(selected_index)
        write_json_atomic(PENDING_QUEUE_FILE, queue)
        return job


def _normalized_timeline(speech: dict[str, Any]) -> dict[str, Any]:
    timeline = speech.get("timeline")
    if isinstance(timeline, dict):
        segments_raw = timeline.get("segments", [])
        timeline_end = timeline.get("timeline_end", 0.0)
        speech_end = timeline.get("speech_end", timeline_end)
        trailing_mute_at = timeline.get("trailing_mute_at", speech_end)
    else:
        segments_raw = timeline if isinstance(timeline, list) else []
        timeline_end = speech.get("timeline_end", 0.0)
        speech_end = speech.get("speech_end", timeline_end)
        trailing_mute_at = speech.get("trailing_mute_at", speech_end)

    segments: list[dict[str, Any]] = []
    for segment in segments_raw:
        if isinstance(segment, MicroSegment):
            segments.append(segment.to_dict())
        elif isinstance(segment, dict):
            segments.append(dict(segment))

    try:
        timeline_end_float = float(timeline_end or 0.0)
    except (TypeError, ValueError):
        timeline_end_float = 0.0

    try:
        speech_end_float = float(speech_end or timeline_end_float)
    except (TypeError, ValueError):
        speech_end_float = timeline_end_float

    try:
        trailing_mute_at_float = float(trailing_mute_at or speech_end_float)
    except (TypeError, ValueError):
        trailing_mute_at_float = speech_end_float

    return {
        "segments": segments,
        "timeline_end": timeline_end_float,
        "speech_end": speech_end_float,
        "trailing_mute_at": trailing_mute_at_float,
    }


def _active_job_stale_after(job: dict[str, Any]) -> float:
    timeline = job.get("timeline")
    timeline_end = 0.0
    if isinstance(timeline, dict):
        try:
            timeline_end = float(
                timeline.get("timeline_end")
                or timeline.get("speech_end")
                or 0.0
            )
        except (TypeError, ValueError):
            timeline_end = 0.0

    return max(
        ACTIVE_JOB_MIN_MAX_AGE_SECONDS,
        timeline_end + ACTIVE_JOB_STALE_GRACE_SECONDS,
    )


def _active_job_started_at(job: dict[str, Any]) -> float:
    for value in (
        job.get("activated_at"),
        job.get("prepared_at"),
        _job_metadata(job).get("prepared_at"),
        job.get("created_at"),
    ):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0.0:
            return number
    return 0.0


def _active_job_is_stale(job: dict[str, Any]) -> bool:
    started_at = _active_job_started_at(job)
    if started_at <= 0.0:
        return False
    return _now() - started_at > _active_job_stale_after(job)


def prepare_pending_job(job: dict[str, Any]) -> dict[str, Any]:
    metadata = _job_metadata(job)
    voice_path_text = str(metadata.get("voice_path") or "").strip()
    voice_path = (
        Path(voice_path_text)
        if voice_path_text
        else spectator_voices.voice_path_for_metadata(metadata)
    )
    speech = synthesize_for_job(
        str(job.get("text") or ""),
        voice_path=voice_path if voice_path and voice_path.is_file() else None,
    )
    prepared_metadata = {
        **metadata,
        "prepared_at": _now(),
        "timeline_path": speech.get("timeline_path", ""),
        "voice_path": speech.get("voice_path", ""),
    }

    ready = dict(job)
    ready.update(
        {
            "audio_path": speech["audio_path"],
            "timeline_path": speech["timeline_path"],
            "timeline": _normalized_timeline(speech),
            "metadata": prepared_metadata,
            "prepared_at": _now(),
        }
    )
    return ready


def _release_complete_pairs(
    pair_state: dict[str, Any],
    ready_queue: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pairs = pair_state.get("pairs", {})
    order = list(pair_state.get("order") or [])
    remaining_order: list[str] = []
    now = _now()
    changed = False

    for sequence_id in order:
        pair = pairs.get(sequence_id)
        if not isinstance(pair, dict):
            changed = True
            continue

        pair_created_at = float(pair.get("created_at") or now)
        if now - pair_created_at > PAIR_JOB_MAX_AGE_SECONDS:
            user_job = pair.get("user")
            response_job = pair.get("response")
            if isinstance(user_job, dict):
                ready_queue.append(user_job)
            if isinstance(response_job, dict):
                ready_queue.append(response_job)
            pairs.pop(sequence_id, None)
            changed = True
            continue

        user_job = pair.get("user")
        response_job = pair.get("response")
        if isinstance(user_job, dict) and isinstance(response_job, dict):
            pair_id = str(pair.get("pair_id") or sequence_id)
            ready_queue.extend(
                [
                    {
                        **user_job,
                        "pair_playback_id": pair_id,
                        "pair_playback_part": "user",
                        "pair_playback_index": 0,
                        "pair_playback_total": 2,
                    },
                    {
                        **response_job,
                        "pair_playback_id": pair_id,
                        "pair_playback_part": "response",
                        "pair_playback_index": 1,
                        "pair_playback_total": 2,
                    },
                ]
            )
            pairs.pop(sequence_id, None)
            changed = True
            continue

        remaining_order.append(sequence_id)

    if changed:
        pair_state = {"pairs": pairs, "order": remaining_order, "updated_at": now}
    return pair_state, ready_queue


def _push_chat_reference_pair_ready(job: dict[str, Any]) -> None:
    if not _job_survives_reset(job):
        return

    sequence_id = _chat_reference_sequence_id(job)
    part = _chat_reference_part(job)
    if not sequence_id or part not in {"user", "response"}:
        return

    pair_state = _read_pair_queue()
    pairs = pair_state.get("pairs", {})
    order = list(pair_state.get("order") or [])
    pair = dict(pairs.get(sequence_id) or {})
    if not pair:
        pair = {"pair_id": uuid.uuid4().hex, "created_at": _job_created_at(job) or _now()}
        if sequence_id not in order:
            order.append(sequence_id)

    pair[part] = dict(job)
    pair["updated_at"] = _now()
    pairs[sequence_id] = pair
    pair_state = {"pairs": pairs, "order": order, "updated_at": _now()}

    ready_queue = _drop_jobs_before_reset(
        _prune_old_jobs(
            _read_list(READY_QUEUE_FILE),
            max_age=READY_JOB_MAX_AGE_SECONDS,
        )
    )
    pair_state, ready_queue = _release_complete_pairs(pair_state, ready_queue)
    write_json_atomic(READY_QUEUE_FILE, _sort_jobs(ready_queue)[:100])
    _write_pair_queue(pair_state)


def push_ready(job: dict[str, Any]) -> None:
    with _LOCK:
        if not _job_survives_reset(job):
            return

        if _is_chat_reference_pair_job(job):
            _push_chat_reference_pair_ready(dict(job))
            return

        queue = _drop_jobs_before_reset(
            _prune_old_jobs(
                _read_list(READY_QUEUE_FILE),
                max_age=READY_JOB_MAX_AGE_SECONDS,
            )
        )
        queue.append(dict(job))
        write_json_atomic(READY_QUEUE_FILE, _sort_jobs(queue)[:100])


def active_job() -> dict[str, Any] | None:
    raw = read_json(ACTIVE_SPEECH_FILE, {})
    if not isinstance(raw, dict) or not raw:
        return None
    if _active_job_is_stale(raw):
        write_json_atomic(ACTIVE_SPEECH_FILE, {})
        return None
    return dict(raw)


def _select_ready_job(ready: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    manual_sequence = _read_manual_sequence()
    if bool(manual_sequence.get("active")):
        sequence_id = str(manual_sequence.get("id") or "")
        matches = [
            (index, job)
            for index, job in enumerate(ready)
            if isinstance(job, dict)
            and _manual_job_matches(job, sequence_id)
        ]
        if not matches:
            manual_sequence = _expire_manual_sequence_if_orphaned(
                manual_sequence,
                pending=_read_list(PENDING_QUEUE_FILE),
                ready=ready,
                active=active_job(),
            )
            if not bool(manual_sequence.get("active")):
                if not ready:
                    return None, ready
                return ready.pop(0), ready
            return None, ready

        selected_index, job = min(
            matches,
            key=lambda pair: int(
                _job_metadata(pair[1]).get("manual_sequence_index")
                or 0
            ),
        )
        return ready.pop(selected_index), ready

    active_pair = _active_pair_playback()
    active_pair_id = str(active_pair.get("pair_playback_id") or "").strip()
    active_next_index = int(active_pair.get("next_index") or 0)
    if active_pair_id:
        for index, job in enumerate(ready):
            if str(job.get("pair_playback_id") or "") != active_pair_id:
                continue
            if int(job.get("pair_playback_index") or 0) != active_next_index:
                continue
            return ready.pop(index), ready
        _write_pair_playback({})

    if not ready:
        return None, ready
    return ready.pop(0), ready


def _update_pair_playback_after_pop(job: dict[str, Any]) -> None:
    pair_id = str(job.get("pair_playback_id") or "").strip()
    if not pair_id:
        return
    index = int(job.get("pair_playback_index") or 0)
    total = int(job.get("pair_playback_total") or 0)
    next_index = index + 1
    if total > 0 and next_index < total:
        _write_pair_playback(
            {
                "pair_playback_id": pair_id,
                "next_index": next_index,
                "total": total,
                "updated_at": _now(),
            }
        )
    else:
        _write_pair_playback({})


def pop_next() -> dict[str, Any] | None:
    with _LOCK:
        if active_job() is not None:
            return None

        ready = _sort_jobs(
            _drop_jobs_before_reset(
                _prune_old_jobs(
                    _read_list(READY_QUEUE_FILE),
                    max_age=READY_JOB_MAX_AGE_SECONDS,
                )
            )
        )
        job, ready = _select_ready_job(ready)
        if job is None:
            write_json_atomic(READY_QUEUE_FILE, ready)
            return None

        write_json_atomic(READY_QUEUE_FILE, ready)
        job["activated_at"] = _now()
        write_json_atomic(ACTIVE_SPEECH_FILE, job)
        _update_pair_playback_after_pop(job)
        return job


def return_active_to_ready(job_id: str) -> bool:
    with _LOCK:
        current = active_job()
        if current is None or str(current.get("id") or "") != str(job_id or ""):
            return False
        write_json_atomic(ACTIVE_SPEECH_FILE, {})
        current.pop("activated_at", None)
        push_ready(current)
        return True


def acknowledge_speech_finished(
    job_id: str,
    *,
    sequence_id: str = "",
    sequence_index: int | None = None,
) -> dict[str, Any]:
    with _LOCK:
        current = active_job()
        if current is None or str(current.get("id") or "") != str(job_id or ""):
            return {
                "ok": False,
                "acknowledged": False,
                "manual_sequence": manual_sequence_status(),
            }
        write_json_atomic(ACTIVE_SPEECH_FILE, {})

        metadata = _job_metadata(current)
        clean_sequence_id = str(
            sequence_id
            or metadata.get("manual_sequence_id")
            or ""
        ).strip()

        if sequence_index is None:
            sequence_index = metadata.get("manual_sequence_index")

        manual_result = _acknowledge_manual_sequence_part(
            clean_sequence_id,
            sequence_index,
            job_id=job_id,
        )

        return {
            "ok": True,
            "acknowledged": True,
            "manual_sequence": manual_result,
        }


def _acknowledge_manual_sequence_part(
    sequence_id: str,
    sequence_index: Any,
    *,
    job_id: str,
) -> dict[str, Any]:
    state = _read_manual_sequence()
    if not bool(state.get("active")):
        return _public_manual_sequence(state)

    if not sequence_id or sequence_id != str(state.get("id") or ""):
        return _public_manual_sequence(state)

    try:
        index = int(sequence_index)
    except (TypeError, ValueError):
        return _public_manual_sequence(state)

    chunks = state.get("chunks")
    chunks = chunks if isinstance(chunks, list) else []
    if index < 0 or index >= len(chunks):
        return _public_manual_sequence(state)

    last_finished = int(
        state.get("last_finished_index")
        if state.get("last_finished_index") is not None
        else -1
    )

    if index > last_finished:
        state["last_finished_index"] = index
        state["last_finished_job_id"] = str(job_id or "")
        state["last_finished_at"] = _now()
        state["updated_at"] = _now()

    if index >= len(chunks) - 1:
        state["active"] = False
        state["completed_at"] = _now()
        state["updated_at"] = _now()
    else:
        _fill_manual_sequence_window(state)

    write_json_atomic(MANUAL_SEQUENCE_FILE, state)
    return _public_manual_sequence(state)


def status() -> dict[str, Any]:
    with _LOCK:
        pending = _sort_jobs(
            _drop_jobs_before_reset(
                _prune_old_jobs(
                    _read_list(PENDING_QUEUE_FILE),
                    max_age=PENDING_JOB_MAX_AGE_SECONDS,
                )
            )
        )
        ready = _sort_jobs(
            _drop_jobs_before_reset(
                _prune_old_jobs(
                    _read_list(READY_QUEUE_FILE),
                    max_age=READY_JOB_MAX_AGE_SECONDS,
                )
            )
        )
        pair_state = _read_pair_queue()
        original_pair_state = dict(pair_state)
        pair_state, ready = _release_complete_pairs(
            pair_state,
            ready,
        )
        ready = _sort_jobs(
            _drop_jobs_before_reset(
                _prune_old_jobs(
                    ready,
                    max_age=READY_JOB_MAX_AGE_SECONDS,
                )
            )
        )
        write_json_atomic(PENDING_QUEUE_FILE, pending)
        write_json_atomic(READY_QUEUE_FILE, ready)
        if pair_state != original_pair_state:
            _write_pair_queue(pair_state)
        active = active_job()
        manual_sequence = _expire_manual_sequence_if_orphaned(
            _read_manual_sequence(),
            pending=pending,
            ready=ready,
            active=active,
        )
        active_pair = _active_pair_playback()

    pairs = pair_state.get("pairs", {})
    return {
        "pending_size": len(pending),
        "ready_size": len(ready),
        "pair_waiting_size": len(pairs) if isinstance(pairs, dict) else 0,
        "active_pair": active_pair,
        "active": active,
        "next_pending": pending[0] if pending else None,
        "next_ready": ready[0] if ready else None,
        "manual_sequence": _public_manual_sequence(manual_sequence),
        "reset_at": _last_reset_at(),
    }
