from cobrinha_server.services import (
    music_runtime,
)


def test_session_start_track_is_randomized_and_persisted(
    tmp_path,
    monkeypatch,
):
    music_dir = tmp_path / "music"
    music_dir.mkdir()

    first = music_dir / "01-first.mp3"
    second = music_dir / "02-second.mp3"
    first.write_bytes(b"")
    second.write_bytes(b"")

    runtime_file = tmp_path / "music_runtime.json"
    runtime_file.write_text(
        (
            '{"enabled": true, "volume": 0.25, '
            f'"current_track": "{first}"}}'
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        music_runtime,
        "BACKGROUND_MUSIC_DIR",
        music_dir,
    )
    monkeypatch.setattr(
        music_runtime,
        "MUSIC_RUNTIME_FILE",
        runtime_file,
    )
    monkeypatch.setattr(
        music_runtime.random,
        "choice",
        lambda candidates: candidates[0],
    )

    state = (
        music_runtime.choose_session_start_track()
    )

    assert state["enabled"] is True
    assert state["volume"] == music_runtime.DEFAULT_VOLUME
    assert state["current_track"] == str(
        second.resolve()
    )
    assert (
        music_runtime.status()["current_track"]
        == str(second.resolve())
    )


def test_track_entries_ignore_unsupported_files(
    tmp_path,
    monkeypatch,
):
    music_dir = tmp_path / "music"
    music_dir.mkdir()

    source = music_dir / "pacote" / "minha-musica.mp3"
    source.parent.mkdir()
    source.write_bytes(b"source")
    (music_dir / "notas.txt").write_text(
        "ignorar",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        music_runtime,
        "BACKGROUND_MUSIC_DIR",
        music_dir,
    )

    entries = music_runtime.track_entries()

    assert len(entries) == 1
    assert entries[0]["processed"] is False
    assert entries[0]["source_path"] == str(source.resolve())
