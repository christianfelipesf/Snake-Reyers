from cobrinha_server.services import top_supporters


def _patch_state(monkeypatch, tmp_path):
    state_file = tmp_path / "top_supporters_live.json"
    monkeypatch.setattr(
        top_supporters,
        "TOP_SUPPORTERS_FILE",
        state_file,
    )
    top_supporters.reset()
    return state_file


def test_activity_points_and_active_top(monkeypatch, tmp_path):
    _patch_state(monkeypatch, tmp_path)

    like = top_supporters.record_like(
        {
            "user_id": "u1",
            "username": "ana",
            "display_name": "Ana",
            "count": 2,
        }
    )
    assert like["points_added"] == 40

    share = top_supporters.record_share(
        {
            "user_id": "u1",
            "username": "ana",
            "display_name": "Ana",
        }
    )
    assert share["points_added"] == 40

    gift = top_supporters.record_gift(
        {
            "user_id": "u2",
            "username": "joao",
            "display_name": "Joao",
            "text": "Doughnut",
            "metadata": {
                "gift_name": "Doughnut",
                "count": 1,
                "gift_total_coins": 30,
            },
        }
    )
    assert gift["points_added"] == 3000

    entries = top_supporters.public_entries()
    assert entries[0]["display_name"] == "Joao"
    assert entries[0]["points"] == 3000
    assert entries[1]["display_name"] == "Ana"
    assert entries[1]["points"] == 80


def test_inactive_user_leaves_visible_top(monkeypatch, tmp_path):
    _patch_state(monkeypatch, tmp_path)
    now = [1000.0]
    monkeypatch.setattr(
        top_supporters.time,
        "time",
        lambda: now[0],
    )

    top_supporters.record_like(
        {
            "user_id": "u1",
            "username": "ana",
            "display_name": "Ana",
        }
    )
    assert len(top_supporters.public_entries()) == 1

    now[0] += (
        top_supporters.INACTIVE_AFTER_SECONDS
        + 1.0
    )
    assert top_supporters.public_entries() == []

    top_supporters.record_share(
        {
            "user_id": "u1",
            "username": "ana",
            "display_name": "Ana",
        }
    )
    assert top_supporters.public_entries()[0]["display_name"] == "Ana"


def test_top_comment_waits_for_three_normal_chats(monkeypatch, tmp_path):
    _patch_state(monkeypatch, tmp_path)
    top_supporters.record_gift(
        {
            "user_id": "vip",
            "username": "vip",
            "display_name": "Vip",
            "text": "Rose",
            "metadata": {
                "gift_name": "Rose",
                "count": 1,
                "gift_total_coins": 1,
            },
        }
    )

    for index in range(3):
        event, _remaining = top_supporters.choose_comment(
            [
                {
                    "id": f"n{index}",
                    "kind": "comment",
                    "user_id": f"normal-{index}",
                    "username": f"normal-{index}",
                    "display_name": f"Normal {index}",
                    "text": "oi",
                    "created_at": float(index),
                }
            ]
        )
        assert event["user_id"] == f"normal-{index}"

    vip_event, remaining = top_supporters.choose_comment(
        [
            {
                "id": "normal-final",
                "kind": "comment",
                "user_id": "normal-final",
                "username": "normal-final",
                "display_name": "Normal final",
                "text": "normal",
                "created_at": 4.0,
            },
            {
                "id": "vip-1",
                "kind": "comment",
                "user_id": "vip",
                "username": "vip",
                "display_name": "Vip",
                "text": "vip",
                "created_at": 5.0,
            },
        ]
    )

    assert vip_event["user_id"] == "vip"
    assert vip_event["metadata"]["top_supporter_priority"] is True
    assert len(remaining) == 1
    assert remaining[0]["user_id"] == "normal-final"
