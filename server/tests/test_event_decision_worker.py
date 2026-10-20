import asyncio

from cobrinha_server.services import event_decision_worker


def _gift_event(name: str) -> dict:
    return {
        "text": name,
        "metadata": {
            "gift_name": name,
            "count": 1,
            "gift_total_coins": 1,
        },
    }


def test_gift_thank_cooldown_is_per_gift(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(
        event_decision_worker.time,
        "time",
        lambda: now[0],
    )
    event_decision_worker._LAST_GIFT_THANK_AT_BY_KEY.clear()

    rose_key = event_decision_worker._gift_key(
        _gift_event("Rose")
    )
    tiktok_key = event_decision_worker._gift_key(
        _gift_event("TikTok")
    )

    should_thank, _reason = event_decision_worker._should_thank_individual_gift(
        _gift_event("Rose"),
        comments_pending=0,
        gifts_pending=0,
        gift_key=rose_key,
    )
    assert should_thank is True

    event_decision_worker._mark_gift_thanked(rose_key)

    should_thank, reason = event_decision_worker._should_thank_individual_gift(
        _gift_event("Rose"),
        comments_pending=0,
        gifts_pending=0,
        gift_key=rose_key,
    )
    assert should_thank is False
    assert reason == "cooldown"

    should_thank, _reason = event_decision_worker._should_thank_individual_gift(
        _gift_event("TikTok"),
        comments_pending=0,
        gifts_pending=0,
        gift_key=tiktok_key,
    )
    assert should_thank is True


def test_reset_transient_state_clears_gift_buffers(monkeypatch, tmp_path):
    monkeypatch.setattr(
        event_decision_worker,
        "WORKER_STATUS_FILE",
        tmp_path / "event_decision_worker_status.json",
    )
    event_decision_worker._GIFT_THANK_BUFFER.append(
        {"gift_key": "rose", "display_name": "Ana"}
    )
    event_decision_worker._LAST_GIFT_THANK_AT_BY_KEY["rose"] = 1000.0

    state = event_decision_worker.reset_transient_state(
        reason="test_reset",
    )

    assert event_decision_worker._GIFT_THANK_BUFFER == []
    assert event_decision_worker._LAST_GIFT_THANK_AT_BY_KEY == {}
    assert state["last_action"] == "test_reset"
    assert state["events_processed"] == 0


def test_heart_me_band_user_payload_includes_avatar():
    event = {
        "id": "gift-1",
        "kind": "gift",
        "text": "Heart Me",
        "user_id": "user-1",
        "username": "ana_live",
        "display_name": "Ana",
        "avatar_url": "https://example.test/avatar.png",
        "metadata": {
            "gift_name": "Heart Me",
            "count": 2,
        },
    }
    gift_key = event_decision_worker._gift_key(event)

    assert event_decision_worker._is_heart_me_band_gift_key(gift_key)

    payload = event_decision_worker._heart_me_band_user_payload(
        event,
        avatar_path="/tmp/avatar.png",
        display_name="Ana",
        user_key="user-1",
        gift_key=gift_key,
    )

    assert payload["heart_me_band"] is True
    assert payload["gift_key"] == "heart-me"
    assert payload["gift_count"] == 2
    assert payload["avatar_path"] == "/tmp/avatar.png"
    assert payload["display_name"] == "Ana"


def test_loop_records_exception_and_keeps_running(monkeypatch, tmp_path):
    monkeypatch.setattr(
        event_decision_worker,
        "WORKER_STATUS_FILE",
        tmp_path / "event_decision_worker_status.json",
    )
    calls = {"count": 0}

    async def fake_process_once():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        raise asyncio.CancelledError()

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(
        event_decision_worker,
        "process_once",
        fake_process_once,
    )
    monkeypatch.setattr(
        event_decision_worker.asyncio,
        "sleep",
        fake_sleep,
    )

    try:
        asyncio.run(event_decision_worker._loop())
    except asyncio.CancelledError:
        pass

    state = event_decision_worker.status()
    assert calls["count"] == 2
    assert state["last_action"] == "loop_error"
    assert "RuntimeError: boom" in state["last_error"]
