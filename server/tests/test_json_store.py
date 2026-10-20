import json

from cobrinha_server.core import json_store


def test_write_json_atomic_retries_windows_permission_error(monkeypatch, tmp_path):
    target = tmp_path / "state.json"
    real_replace = json_store.os.replace
    attempts = 0

    def flaky_replace(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("temporarily locked")
        real_replace(source, destination)

    monkeypatch.setattr(json_store.os, "replace", flaky_replace)
    monkeypatch.setattr(json_store.time, "sleep", lambda _seconds: None)

    json_store.write_json_atomic(target, {"state": "ready"})

    assert attempts == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "ready"}
    assert list(tmp_path.iterdir()) == [target]
