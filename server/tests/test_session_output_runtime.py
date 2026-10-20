from cobrinha_server.services import (
    session_executor_plan,
    session_runtime_orchestrator as orchestrator,
)
from cobrinha_server.services.output_metrics import (
    evaluate,
)
from cobrinha_server.services.session_executor_plan import (
    build_identity,
)
from cobrinha_server.services.session_runtime_adapters import (
    audio_prepare_spec,
    capture_start_spec,
)


def _arg_after(
    argv: tuple[str, ...],
    name: str,
) -> str:
    index = argv.index(name)
    return argv[index + 1]


def test_windows_always_uses_packaged_game(monkeypatch, tmp_path):
    game = tmp_path / "game" / "windows" / "SnakeReyers.exe"
    monkeypatch.setattr(session_executor_plan.os, "name", "nt")
    monkeypatch.setattr(
        session_executor_plan,
        "EXPORTED_GAME_EXECUTABLE",
        game,
    )

    selected = session_executor_plan.preferred_live_executable(
        "/snap/bin/godot-4",
        "editor",
    )

    assert selected == str(game)


def test_capture_spec_uses_stable_tiktok_audio_and_no_ack_restart():
    identity = build_identity(
        "unit-live"
    )
    audio_spec = audio_prepare_spec(
        identity
    )

    assert "rate=48000" in audio_spec.argv

    capture_spec = capture_start_spec(
        display_value=":99",
        audio_monitor=identity.audio_monitor,
        destination_url="rtmp://example.test/live/key",
        encoder="nvenc",
        sink="rtmp2sink",
        bitrate_kbps=3100,
        window_xid=123,
        rtmp_no_ack_timeout=65.0,
    )

    assert (
        _arg_after(
            capture_spec.argv,
            "--audio-rate",
        )
        == "48000"
    )
    assert (
        _arg_after(
            capture_spec.argv,
            "--audio-bitrate",
        )
        == "160000"
    )
    assert (
        _arg_after(
            capture_spec.argv,
            "--rtmp-restart-max",
        )
        == "0"
    )
    assert (
        "--rtmp-fail-on-ack-lag"
        not in capture_spec.argv
    )


def test_initial_ack_pending_keeps_capture_running():
    assert orchestrator._initial_ack_can_keep_running(
        {"reason": "no_initial_ack"}
    )
    assert orchestrator._initial_ack_can_keep_running(
        {"error": "sem ACK inicial no_ack_seconds=45"}
    )
    assert orchestrator._initial_ack_can_keep_running(
        {"error": "rtmp_ack_missing"}
    )
    assert not orchestrator._initial_ack_can_keep_running(
        {"reason": "capture_exited"}
    )


def test_output_metrics_treat_initial_ack_as_pending_not_fatal():
    metrics = evaluate(
        {
            "now": 50.0,
            "started_at": 1.0,
            "first_stat_at": 1.0,
            "last_ack_at": 0.0,
            "out_total": 5_000_001,
            "out_acked": 0,
            "clock_name": "GstPulseSrcClock",
            "no_ack_timeout": 35.0,
            "no_ack_min_bytes": 5_000_000,
        }
    )

    assert metrics["healthy"] is True
    assert metrics["reason"] == "remote_ack_pending"
    assert metrics["remote_ack"]["no_initial_ack"] is True
