from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from cobrinha_server.routes import panel
from cobrinha_server.services import system_updates


def _reset_state() -> None:
    with system_updates._state_lock:
        system_updates._state.update(
            {
                "busy": False,
                "checked_at": "",
                "available": "",
                "update_available": False,
                "installed": False,
                "restart_scheduled": False,
                "message": "Atualização ainda não consultada.",
                "last_error": "",
            }
        )


def test_system_update_check_reports_available_version(monkeypatch):
    _reset_state()
    updater = SimpleNamespace(
        _manifest_url=lambda: "https://example.test/update.json",
        check_and_update=lambda url, install: {
            "current": "0.1.4",
            "available": "0.1.5",
            "update_available": True,
            "installed": False,
        },
    )
    monkeypatch.setattr(system_updates, "_load_updater", lambda: updater)
    monkeypatch.setattr(system_updates, "application_version", lambda: "0.1.4")

    result = system_updates.synchronize(install=False)

    assert result["current"] == "0.1.4"
    assert result["available"] == "0.1.5"
    assert result["update_available"] is True
    assert result["installed"] is False


def test_system_update_install_reports_restart_ready(monkeypatch):
    _reset_state()
    updater = SimpleNamespace(
        _manifest_url=lambda: "https://example.test/update.json",
        check_and_update=lambda url, install: {
            "current": "0.1.4",
            "available": "0.1.5",
            "update_available": True,
            "installed": install,
            "files_updated": 12,
        },
    )
    monkeypatch.setattr(system_updates, "_load_updater", lambda: updater)

    result = system_updates.synchronize(install=True)

    assert result["installed"] is True
    assert "reiniciado" in result["message"]


def test_schedule_restart_spawns_helper_and_delays_exit(monkeypatch, tmp_path):
    _reset_state()
    restarter = tmp_path / "restart.py"
    restarter.write_text("# test\n", encoding="utf-8")
    spawned = {}
    timer = SimpleNamespace(daemon=False, start=lambda: spawned.update(timer=True))

    monkeypatch.setattr(system_updates, "RESTARTER_PATH", restarter)
    monkeypatch.setattr(
        system_updates.subprocess,
        "Popen",
        lambda command, **kwargs: spawned.update(command=command, kwargs=kwargs),
    )
    monkeypatch.setattr(
        system_updates.threading,
        "Timer",
        lambda *args, **kwargs: timer,
    )

    system_updates.schedule_restart(delay_seconds=0.1)

    assert str(restarter) in spawned["command"]
    assert spawned["timer"] is True
    assert system_updates.public_status()["restart_scheduled"] is True


def test_install_endpoint_blocks_open_game(monkeypatch):
    _reset_state()
    monkeypatch.setattr(panel, "_live_runtime_active", lambda: True)

    response = asyncio.run(panel.api_system_updates_install())
    payload = json.loads(response.body)

    assert response.status_code == 409
    assert payload["ok"] is False
    assert "Feche o jogo" in payload["error"]
