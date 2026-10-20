from __future__ import annotations

from typing import Any

from cobrinha_server.services import (
    event_decision_worker,
    live_events,
    top_supporters,
    tts_worker,
)
from cobrinha_server.services.speech_queue import (
    reset_speech_queues,
    status as speech_queue_status,
)


def reset_live_transient_state(
    *,
    reason: str = "live_session_reset",
) -> dict[str, Any]:
    clean_reason = str(reason or "live_session_reset").strip() or "live_session_reset"

    reset_speech_queues()
    live_events.reset()
    top_supporters.reset()
    worker = event_decision_worker.reset_transient_state(
        reason=clean_reason,
    )
    tts = tts_worker.reset_transient_state(
        reason=clean_reason,
    )

    return {
        "ok": True,
        "reason": clean_reason,
        "speech_queue": speech_queue_status(),
        "events": live_events.status(),
        "top_supporters": top_supporters.status(),
        "event_decision_worker": worker,
        "tts_worker": tts,
    }
