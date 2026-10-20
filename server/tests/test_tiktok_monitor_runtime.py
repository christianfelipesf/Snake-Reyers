from subprocess import CompletedProcess

from cobrinha_server.services import tiktok_monitor_runtime
from cobrinha_server.services import tiktok_monitor


def test_windows_pid_check_uses_tasklist_without_signaling_process(monkeypatch):
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return CompletedProcess(
            arguments,
            0,
            stdout='"node.exe","4321","Console","1","50,000 K"\n',
            stderr="",
        )

    monkeypatch.setattr(tiktok_monitor_runtime.os, "name", "nt")
    monkeypatch.setattr(tiktok_monitor_runtime.subprocess, "run", fake_run)

    assert tiktok_monitor_runtime._pid_exists(4321) is True
    assert calls[0][0][:3] == ["tasklist", "/FI", "PID eq 4321"]
    assert "creationflags" in calls[0][1]


def test_windows_pid_check_rejects_missing_process(monkeypatch):
    def fake_run(arguments, **kwargs):
        return CompletedProcess(
            arguments,
            0,
            stdout="INFO: No tasks are running which match the specified criteria.\n",
            stderr="",
        )

    monkeypatch.setattr(tiktok_monitor_runtime.os, "name", "nt")
    monkeypatch.setattr(tiktok_monitor_runtime.subprocess, "run", fake_run)

    assert tiktok_monitor_runtime._pid_exists(4321) is False


def test_room_id_error_names_the_live_user():
    message = tiktok_monitor._friendly_connection_error(
        "Failed to retrieve Room ID from all sources.",
        username="criador_exemplo",
    )

    assert "@criador_exemplo" in message
    assert "Live nao encontrada" in message


def test_rate_limit_error_tells_user_not_to_reconnect_repeatedly():
    message = tiktok_monitor._friendly_connection_error(
        "SignatureRateLimitError rate_limit_account_hour",
        username="criador_exemplo",
    )

    assert "Limite temporario" in message
    assert "nao reinicie" in message


def test_monitor_readiness_does_not_require_proxy(monkeypatch):
    monkeypatch.setattr(
        tiktok_monitor_runtime,
        "node_source_status",
        lambda: {
            "directory_exists": True,
            "entry_exists": True,
            "package_exists": True,
            "node_binary": "node",
            "node_modules_exists": True,
        },
    )
    monkeypatch.setattr(
        tiktok_monitor_runtime,
        "local_server_status",
        lambda: {},
    )

    state = tiktok_monitor_runtime.readiness()

    assert state["ready_to_launch"] is True
    assert "tor_ready" not in state
    assert "tor" not in state
