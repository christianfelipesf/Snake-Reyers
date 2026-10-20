import json
from pathlib import Path

from cobrinha_server.services import runtime_cleanup


def _write(path: Path, data: bytes = b"data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_cleanup_removes_transient_files_and_keeps_references(
    monkeypatch,
    tmp_path,
):
    runs = tmp_path / "runs"
    prepared = runs / "prepared_audio"
    avatars = runs / "profile_avatars"
    logs = runs / "logs"

    protected_audio = prepared / "speech_current.wav"
    stale_audio = prepared / "speech_old.wav"
    stale_timeline = prepared / "speech_old.json"
    stale_avatar = avatars / "avatar.webp"
    stale_log = logs / "output.log"
    server_log = logs / "cobrinha_server.log"
    temp_file = runs / "tmp_abandoned"

    for path in (
        protected_audio,
        stale_audio,
        stale_timeline,
        stale_avatar,
        stale_log,
        server_log,
        temp_file,
    ):
        _write(path)

    active_file = runs / "speech_active.json"
    active_file.write_text(
        json.dumps({"audio_path": str(protected_audio)}),
        encoding="utf-8",
    )

    monkeypatch.setattr(runtime_cleanup, "RUNS_DIR", runs)
    monkeypatch.setattr(runtime_cleanup, "LOGS_DIR", logs)
    monkeypatch.setattr(runtime_cleanup, "PREPARED_AUDIO_DIR", prepared)
    monkeypatch.setattr(runtime_cleanup, "PROFILE_AVATAR_DIR", avatars)
    monkeypatch.setattr(runtime_cleanup, "SPEECH_TEST_DIR", runs / "speech_test")
    monkeypatch.setattr(runtime_cleanup, "STATE_FILE", runs / "runtime_cleanup.json")
    monkeypatch.setattr(runtime_cleanup, "REFERENCE_STATE_FILES", (active_file,))

    result = runtime_cleanup.cleanup()

    assert result["ok"] is True
    assert protected_audio.exists()
    assert not server_log.exists()
    assert not stale_audio.exists()
    assert not stale_timeline.exists()
    assert not stale_avatar.exists()
    assert not stale_log.exists()
    assert not temp_file.exists()
    assert prepared.exists()
    assert avatars.exists()


def _configure_cleanup_paths(monkeypatch, tmp_path):
    runs = tmp_path / "runs"
    monkeypatch.setattr(runtime_cleanup, "RUNS_DIR", runs)
    monkeypatch.setattr(runtime_cleanup, "LOGS_DIR", runs / "logs")
    monkeypatch.setattr(
        runtime_cleanup,
        "PREPARED_AUDIO_DIR",
        runs / "prepared_audio",
    )
    monkeypatch.setattr(
        runtime_cleanup,
        "PROFILE_AVATAR_DIR",
        runs / "profile_avatars",
    )
    monkeypatch.setattr(
        runtime_cleanup,
        "SPEECH_TEST_DIR",
        runs / "speech_test",
    )
    monkeypatch.setattr(
        runtime_cleanup,
        "STATE_FILE",
        runs / "runtime_cleanup.json",
    )
    monkeypatch.setattr(runtime_cleanup, "REFERENCE_STATE_FILES", ())
    return runs


def test_automatic_cleanup_runs_after_every_three_completed_lives(
    monkeypatch,
    tmp_path,
):
    runs = _configure_cleanup_paths(monkeypatch, tmp_path)
    stale_audio = runs / "prepared_audio" / "speech_old.wav"
    _write(stale_audio)

    first = runtime_cleanup.register_completed_live()
    second = runtime_cleanup.register_completed_live()

    assert first["completed_lives"] == 1
    assert second["completed_lives"] == 2
    assert first["cleanup_triggered"] is False
    assert second["cleanup_triggered"] is False
    assert stale_audio.exists()

    third = runtime_cleanup.register_completed_live()

    assert third["ok"] is True
    assert third["cleanup_triggered"] is True
    assert third["completed_lives"] == 0
    assert not stale_audio.exists()

    _write(stale_audio)
    fourth = runtime_cleanup.register_completed_live()

    assert fourth["completed_lives"] == 1
    assert fourth["cleanup_triggered"] is False
    assert stale_audio.exists()
