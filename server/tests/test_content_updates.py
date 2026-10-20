from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from cobrinha_server.services import content_updates


def _catalog(tmp_path: Path, *, target: str = "singing/processed/FANCLUB/test-song") -> Path:
    package = tmp_path / "test-song.zip"
    with zipfile.ZipFile(package, "w") as bundle:
        bundle.writestr("manifest.json", '{"id":"test-song"}\n')
        bundle.writestr("vocals.wav", b"voice")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    manifest = tmp_path / "content-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "revision": 2,
                "items": [
                    {
                        "id": "test-song",
                        "title": "Musica de teste",
                        "type": "gift_song",
                        "version": "1",
                        "url": package.as_uri(),
                        "sha256": digest,
                        "bytes": package.stat().st_size,
                        "target": target,
                        "song_id": "test-song",
                        "gift_names": ["Test Gift"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _configure(tmp_path: Path, monkeypatch, manifest: Path) -> Path:
    assets = tmp_path / "server" / "assets"
    private = tmp_path / "server" / "private"
    config = private / "content-updates.json"
    state = private / "content-update-state.json"
    work = tmp_path / "server" / "runtime" / "content-updates"
    private.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "auto_install": True,
                "manifest_url": manifest.as_uri(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(content_updates, "ASSETS_DIR", assets)
    monkeypatch.setattr(content_updates, "CONFIG_FILE", config)
    monkeypatch.setattr(content_updates, "STATE_FILE", state)
    monkeypatch.setattr(content_updates, "WORK_DIR", work)
    monkeypatch.setattr(content_updates, "_live_active", lambda: False)
    return assets


def test_incremental_content_download_and_install(tmp_path, monkeypatch):
    manifest = _catalog(tmp_path)
    assets = _configure(tmp_path, monkeypatch, manifest)
    registered: list[str] = []
    monkeypatch.setattr(
        content_updates,
        "_register_gift_song",
        lambda item: registered.append(item["song_id"]),
    )

    checked = content_updates.synchronize(install=False)

    assert checked["available_count"] == 1
    assert checked["download_bytes"] > 0
    assert checked["busy"] is False

    installed = content_updates.synchronize(install=True)

    target = assets / "singing" / "processed" / "FANCLUB" / "test-song"
    assert installed["installed_now"] == ["test-song"]
    assert installed["busy"] is False
    assert (target / "vocals.wav").read_bytes() == b"voice"
    assert registered == ["test-song"]
    assert content_updates.synchronize(install=False)["available_count"] == 0


def test_content_install_is_blocked_during_live(tmp_path, monkeypatch):
    manifest = _catalog(tmp_path)
    _configure(tmp_path, monkeypatch, manifest)
    monkeypatch.setattr(content_updates, "_live_active", lambda: True)

    with pytest.raises(content_updates.ContentUpdateBlocked):
        content_updates.synchronize(install=True)


def test_content_target_cannot_leave_allowed_directory(tmp_path, monkeypatch):
    manifest = _catalog(tmp_path, target="singing/other-place")
    _configure(tmp_path, monkeypatch, manifest)

    with pytest.raises(content_updates.ContentUpdateError):
        content_updates.synchronize(install=False)


def test_installed_reaction_matches_normalized_gift_name(tmp_path, monkeypatch):
    manifest = _catalog(tmp_path)
    _configure(tmp_path, monkeypatch, manifest)
    content_updates.STATE_FILE.write_text(
        json.dumps(
            {
                "installed": {
                    "popular-cannon": {
                        "version": "1",
                        "type": "gift_reaction",
                        "gift_names": ["Go Popular"],
                        "action": "gift_cannon",
                        "target": "content/reactions/popular-cannon",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    reaction = content_updates.reaction_for_gift_name("Go Populár")

    assert reaction is not None
    assert reaction["action"] == "gift_cannon"
