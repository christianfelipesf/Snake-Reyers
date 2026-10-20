from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path


def _load_updater():
    updater_path = Path(__file__).resolve().parents[2] / "launcher" / "update.py"
    spec = importlib.util.spec_from_file_location("snake_reyers_updater", updater_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_update_preserves_private_data(tmp_path, monkeypatch):
    updater = _load_updater()
    root = tmp_path / "install"
    root.mkdir()
    (root / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    private = root / "server" / "private"
    private.mkdir(parents=True)
    (private / "keep.txt").write_text("local", encoding="utf-8")

    package = tmp_path / "release.zip"
    with zipfile.ZipFile(package, "w") as bundle:
        bundle.writestr("VERSION", "1.1.0\n")
        bundle.writestr("server/app.txt", "new")
        bundle.writestr("server/private/keep.txt", "remote")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1.1.0",
                "packages": {
                    updater._platform_key(): {
                        "url": package.as_uri(),
                        "sha256": digest,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(updater, "ROOT_DIR", root)
    monkeypatch.setattr(updater, "VERSION_FILE", root / "VERSION")
    monkeypatch.setattr(updater, "UPDATES_DIR", root / "updates")

    result = updater.check_and_update(manifest.as_uri(), install=True)

    assert result["installed"] is True
    assert (root / "VERSION").read_text(encoding="utf-8").strip() == "1.1.0"
    assert (root / "server" / "app.txt").read_text(encoding="utf-8") == "new"
    assert (private / "keep.txt").read_text(encoding="utf-8") == "local"
