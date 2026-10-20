from cobrinha_server.services import live_events, tiktok_monitor


def test_high_value_gift_gets_max_priority(monkeypatch, tmp_path):
    events_file = tmp_path / "social_live_events.json"
    monkeypatch.setattr(
        live_events,
        "SOCIAL_EVENTS_FILE",
        events_file,
    )
    live_events.reset()

    event = live_events.push_gift(
        {
            "user_id": "user-1",
            "username": "ana",
            "display_name": "Ana",
            "gift_name": "Doughnut",
            "diamondCount": 30,
            "repeatCount": 1,
        }
    )

    assert event["priority"] == live_events.HIGH_VALUE_GIFT_PRIORITY
    assert event["metadata"]["high_value_gift"] is True


def test_duplicate_gift_event_id_is_queued_once(monkeypatch, tmp_path):
    events_file = tmp_path / "social_live_events.json"
    monkeypatch.setattr(live_events, "SOCIAL_EVENTS_FILE", events_file)
    live_events.reset()

    payload = {
        "event_id": "tiktok-gift-123",
        "user_id": "user-1",
        "username": "ana",
        "display_name": "Ana",
        "gift_name": "Popular Vote",
        "count": 1,
        "coin_value": 1,
    }

    first = live_events.push_gift(payload)
    duplicate = live_events.push_gift(payload)
    state = live_events.status()

    assert first.get("ignored") is not True
    assert duplicate["ignored"] is True
    assert duplicate["reason"] == "duplicate_gift"
    assert state["gifts_pending"] == 1


def test_tiktok_gift_normalization_preserves_message_id():
    payload = tiktok_monitor.normalize_gift_payload(
        {
            "msgId": "tiktok-message-456",
            "uniqueId": "ana",
            "giftName": "Popular Vote",
            "diamondCount": 1,
        }
    )

    assert payload["event_id"] == "tiktok-message-456"


def test_tiktok_gift_normalization_accepts_current_nested_details():
    payload = tiktok_monitor.normalize_gift_payload(
        {
            "common": {"msgId": "nested-gift-1"},
            "user": {
                "userId": "user-1",
                "uniqueId": "ana",
                "nickname": "Ana",
            },
            "giftDetails": {
                "giftId": "heart-me-id",
                "giftName": "Heart Me",
                "giftType": 1,
                "diamondCount": 1,
            },
            "repeatCount": 2,
            "repeatEnd": True,
        }
    )

    assert payload["event_id"] == "nested-gift-1"
    assert payload["username"] == "ana"
    assert payload["gift_name"] == "Heart Me"
    assert payload["gift_id"] == "heart-me-id"
    assert payload["gift_type"] == 1
    assert payload["coin_value"] == 1
    assert payload["count"] == 2
    assert payload["repeat_end"] is True


def test_tiktok_combo_is_ingested_on_first_update_only(monkeypatch):
    accepted = []
    monkeypatch.setattr(
        tiktok_monitor,
        "ingest_gift",
        lambda payload: accepted.append(payload) or {"ok": True},
    )
    tiktok_monitor._reset_gift_combo_tracking()

    base = {
        "uniqueId": "ana",
        "giftName": "Popular Vote",
        "giftId": "popular-vote",
        "giftType": 1,
        "groupId": "combo-1",
    }

    first = tiktok_monitor.ingest_tiktok_gift(
        {**base, "repeatCount": 1, "repeatEnd": False}
    )
    progress = tiktok_monitor.ingest_tiktok_gift(
        {**base, "repeatCount": 2, "repeatEnd": False}
    )
    finished = tiktok_monitor.ingest_tiktok_gift(
        {**base, "repeatCount": 2, "repeatEnd": True}
    )

    assert first.get("ignored") is not True
    assert progress["ignored"] is True
    assert progress["reason"] == "gift_combo_progress"
    assert finished.get("ignored") is not True
    assert accepted[0]["cannon_only"] is True
    assert accepted[1]["suppress_gift_cannon"] is True
    assert accepted[1]["count"] == 2
    assert len(accepted) == 2


def test_tiktok_new_combo_can_start_immediately_after_previous_final(monkeypatch):
    accepted = []
    monkeypatch.setattr(
        tiktok_monitor,
        "ingest_gift",
        lambda payload: accepted.append(payload) or {"ok": True},
    )
    tiktok_monitor._reset_gift_combo_tracking()

    base = {
        "uniqueId": "ana",
        "giftName": "Popular Vote",
        "giftId": "popular-vote",
        "giftType": 1,
    }
    tiktok_monitor.ingest_tiktok_gift(
        {**base, "repeatCount": 1, "repeatEnd": False}
    )
    tiktok_monitor.ingest_tiktok_gift(
        {**base, "repeatCount": 1, "repeatEnd": True}
    )
    second = tiktok_monitor.ingest_tiktok_gift(
        {**base, "repeatCount": 1, "repeatEnd": False}
    )

    assert second.get("ignored") is not True
    assert accepted[0]["cannon_only"] is True
    assert accepted[1]["suppress_gift_cannon"] is True
    assert accepted[2]["cannon_only"] is True
    assert len(accepted) == 3


def test_tiktok_combo_final_is_accepted_if_it_is_first_packet_seen(monkeypatch):
    accepted = []
    monkeypatch.setattr(
        tiktok_monitor,
        "ingest_gift",
        lambda payload: accepted.append(payload) or {"ok": True},
    )
    tiktok_monitor._reset_gift_combo_tracking()

    result = tiktok_monitor.ingest_tiktok_gift(
        {
            "uniqueId": "ana",
            "giftName": "Popular Vote",
            "giftId": "popular-vote",
            "giftType": 1,
            "groupId": "combo-late",
            "repeatCount": 3,
            "repeatEnd": True,
        }
    )

    assert result.get("ignored") is not True
    assert len(accepted) == 1
