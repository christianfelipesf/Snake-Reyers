import json

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
    assert state["volume"] == 0.25
    assert state["current_track"] == str(
        second.resolve()
    )
    assert (
        music_runtime.status()["current_track"]
        == str(second.resolve())
    )


def test_processed_track_uses_installed_files_when_manifest_paths_are_stale(
    tmp_path,
    monkeypatch,
):
    music_dir = tmp_path / "music" / "background"
    processed_dir = tmp_path / "music" / "background_processed"
    song_dir = processed_dir / "minha-musica"
    music_dir.mkdir(parents=True)
    song_dir.mkdir(parents=True)

    source = music_dir / "minha-musica.mp3"
    source.write_bytes(b"source")
    (song_dir / "vocals.wav").write_bytes(b"voice")
    (song_dir / "instrumental.wav").write_bytes(b"music")
    (song_dir / "vocal_timeline.json").write_text("[]", encoding="utf-8")
    (song_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "minha-musica",
                "title": "Minha Musica",
                "source_path": "/media/maquina-antiga/minha-musica.mp3",
                "files": {
                    "vocal": "/media/maquina-antiga/vocals.wav",
                    "instrumental": "/media/maquina-antiga/instrumental.wav",
                    "timeline": "/media/maquina-antiga/vocal_timeline.json",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(music_runtime, "BACKGROUND_MUSIC_DIR", music_dir)
    monkeypatch.setattr(
        music_runtime,
        "BACKGROUND_MUSIC_PROCESSED_DIR",
        processed_dir,
    )

    entries = music_runtime.track_entries()

    assert len(entries) == 1
    assert entries[0]["processed"] is True
    assert entries[0]["source_path"] == str(source.resolve())
    assert entries[0]["vocal_path"] == str((song_dir / "vocals.wav").resolve())
