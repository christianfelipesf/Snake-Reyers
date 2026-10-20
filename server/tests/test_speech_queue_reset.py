from cobrinha_server.services import speech_queue


def _patch_queue_files(monkeypatch, tmp_path):
    monkeypatch.setattr(
        speech_queue,
        "PENDING_QUEUE_FILE",
        tmp_path / "speech_pending_queue.json",
    )
    monkeypatch.setattr(
        speech_queue,
        "READY_QUEUE_FILE",
        tmp_path / "speech_ready_queue.json",
    )
    monkeypatch.setattr(
        speech_queue,
        "READY_PAIR_QUEUE_FILE",
        tmp_path / "speech_ready_pair_queue.json",
    )
    monkeypatch.setattr(
        speech_queue,
        "PAIR_PLAYBACK_FILE",
        tmp_path / "speech_pair_playback.json",
    )
    monkeypatch.setattr(
        speech_queue,
        "ACTIVE_SPEECH_FILE",
        tmp_path / "speech_active.json",
    )
    monkeypatch.setattr(
        speech_queue,
        "MANUAL_SEQUENCE_FILE",
        tmp_path / "speech_manual_sequence.json",
    )
    monkeypatch.setattr(
        speech_queue,
        "RESET_STATE_FILE",
        tmp_path / "speech_reset_state.json",
    )


def test_reset_blocks_stale_ready_job_from_in_flight_tts(monkeypatch, tmp_path):
    _patch_queue_files(monkeypatch, tmp_path)
    now = [1000.0]
    monkeypatch.setattr(
        speech_queue,
        "_now",
        lambda: now[0],
    )

    speech_queue.reset_speech_queues()

    speech_queue.push_ready(
        {
            "id": "old",
            "text": "fala velha",
            "actor": "main",
            "priority": 80,
            "created_at": 999.0,
            "metadata": {"created_at": 999.0},
        }
    )

    assert speech_queue.status()["ready_size"] == 0

    now[0] = 1001.0
    speech_queue.push_ready(
        {
            "id": "new",
            "text": "fala nova",
            "actor": "main",
            "priority": 80,
            "created_at": 1001.0,
            "metadata": {"created_at": 1001.0},
        }
    )

    state = speech_queue.status()
    assert state["ready_size"] == 1
    assert state["next_ready"]["id"] == "new"
