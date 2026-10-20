from __future__ import annotations

import os
import time
from typing import Any

from cobrinha_server.bridge.godot_bridge import godot_bridge
from cobrinha_server.core.json_store import read_json
from cobrinha_server.core.settings import OUTPUT_METRICS_FILE
from cobrinha_server.services import song_runtime, tiktok_monitor
from cobrinha_server.services.session_runtime_orchestrator import (
    status as runtime_status,
)
from cobrinha_server.services.speech_dispatcher import (
    dispatcher_running,
)
from cobrinha_server.services.speech_queue import (
    status as speech_queue_status,
)


METRICS_FRESH_SECONDS = 15.0
GODOT_STALE_WARNING_SECONDS = 20.0
GODOT_STALE_CRITICAL_SECONDS = 45.0
AUDIO_STALE_SECONDS = 20.0
RTMP_NO_ACK_MIN_BYTES = 5_000_000
RTMP_STALE_ACK_MIN_BYTES = 30_000_000
RTMP_NO_ACK_SECONDS = 35.0
RTMP_STALE_ACK_SECONDS = 45.0
SPEECH_BACKLOG_WARNING_SIZE = 15


def status() -> dict[str, Any]:
    now = time.time()
    runtime = runtime_status()
    metrics = _read_metrics()
    godot = godot_bridge.status()
    speech = speech_queue_status()
    monitor = tiktok_monitor.status()
    issues: list[dict[str, Any]] = []

    runtime_state = str(runtime.get("state") or "stopped")
    capture_pid = _capture_pid(runtime, metrics)
    capture_alive = _process_alive(capture_pid)
    metrics_age = _age(now, metrics.get("updated_at"))
    metrics_fresh = metrics_age <= METRICS_FRESH_SECONDS
    active = bool(
        runtime_state in {"starting", "running"}
        or capture_alive
        or (
            metrics_fresh
            and bool(metrics.get("rtmp_url_present"))
        )
    )

    if not active:
        return {
            "status": "idle",
            "healthy": True,
            "active": False,
            "checked_at": now,
            "issues": [],
            "actions": [],
            "components": _components(
                runtime=runtime,
                metrics=metrics,
                metrics_age=metrics_age,
                capture_pid=capture_pid,
                capture_alive=capture_alive,
                godot=godot,
                speech=speech,
                monitor=monitor,
            ),
        }

    if capture_pid <= 1:
        _add_issue(
            issues,
            "critical",
            "capture_pid_missing",
            "Captura RTMP ativa sem PID conhecido.",
        )
    elif not capture_alive:
        _add_issue(
            issues,
            "critical",
            "capture_process_dead",
            "Processo de captura RTMP nao esta vivo.",
            {"pid": capture_pid},
        )

    if not metrics_fresh:
        _add_issue(
            issues,
            "critical",
            "output_metrics_stale",
            "Metricas de audio/video/RTMP pararam de atualizar.",
            {"age_seconds": round(metrics_age, 1)},
        )

    _check_godot(
        issues,
        now=now,
        godot=godot,
    )
    _check_speech(
        issues,
        now=now,
        speech=speech,
        godot=godot,
    )
    _check_monitor(
        issues,
        runtime=runtime,
        monitor=monitor,
    )
    _check_audio(
        issues,
        now=now,
        metrics=metrics,
        speech=speech,
    )
    _check_rtmp(
        issues,
        metrics=metrics,
    )
    _check_queues(
        issues,
        metrics=metrics,
    )

    level = _overall_status(issues)
    return {
        "status": level,
        "healthy": level == "ok",
        "active": True,
        "checked_at": now,
        "issues": issues,
        "actions": _actions_for(issues),
        "components": _components(
            runtime=runtime,
            metrics=metrics,
            metrics_age=metrics_age,
            capture_pid=capture_pid,
            capture_alive=capture_alive,
            godot=godot,
            speech=speech,
            monitor=monitor,
        ),
    }


def _read_metrics() -> dict[str, Any]:
    payload = read_json(OUTPUT_METRICS_FILE, {})
    return dict(payload) if isinstance(payload, dict) else {}


def _capture_pid(
    runtime: dict[str, Any],
    metrics: dict[str, Any],
) -> int:
    capture = runtime.get("capture")
    if isinstance(capture, dict):
        pid = _int(capture.get("pid"))
        if pid > 1:
            return pid
    return _int(metrics.get("pid"))


def _process_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _check_godot(
    issues: list[dict[str, Any]],
    *,
    now: float,
    godot: dict[str, Any],
) -> None:
    if not bool(godot.get("connected")):
        _add_issue(
            issues,
            "critical",
            "godot_disconnected",
            "Cobrinha/Godot desconectado do servidor.",
        )
        return

    last_message_age = _age(
        now,
        godot.get("last_message_at"),
    )
    if last_message_age >= GODOT_STALE_CRITICAL_SECONDS:
        _add_issue(
            issues,
            "critical",
            "godot_heartbeat_stale",
            "Cobrinha conectada, mas sem heartbeat recente.",
            {"age_seconds": round(last_message_age, 1)},
        )
    elif last_message_age >= GODOT_STALE_WARNING_SECONDS:
        _add_issue(
            issues,
            "warning",
            "godot_heartbeat_slow",
            "Heartbeat da cobrinha esta atrasando.",
            {"age_seconds": round(last_message_age, 1)},
        )


def _check_speech(
    issues: list[dict[str, Any]],
    *,
    now: float,
    speech: dict[str, Any],
    godot: dict[str, Any],
) -> None:
    if not dispatcher_running():
        _add_issue(
            issues,
            "critical",
            "speech_dispatcher_stopped",
            "Despachador de fala nao esta rodando.",
        )

    pending = _int(speech.get("pending_size"))
    ready = _int(speech.get("ready_size"))
    backlog = pending + ready

    if backlog >= SPEECH_BACKLOG_WARNING_SIZE:
        _add_issue(
            issues,
            "warning",
            "speech_backlog_high",
            "Fila de fala esta acumulando muitas mensagens.",
            {"pending": pending, "ready": ready},
        )

    if backlog > 0 and not bool(godot.get("connected")):
        _add_issue(
            issues,
            "critical",
            "speech_waiting_without_godot",
            "Existe fala na fila, mas a cobrinha nao esta conectada.",
            {"pending": pending, "ready": ready},
        )

    active = speech.get("active")
    if not isinstance(active, dict) or not active:
        return

    activated_at = _float(active.get("activated_at"))
    timeline = active.get("timeline")
    timeline_end = 0.0
    if isinstance(timeline, dict):
        timeline_end = _float(
            timeline.get("timeline_end")
            or timeline.get("speech_end")
        )
    stale_after = max(90.0, timeline_end + 45.0)
    active_age = _age(now, activated_at)
    if active_age > stale_after:
        _add_issue(
            issues,
            "critical",
            "speech_active_stale",
            "Uma fala ficou ativa por tempo demais sem finalizar.",
            {
                "job_id": str(active.get("id") or ""),
                "age_seconds": round(active_age, 1),
            },
        )


def _check_monitor(
    issues: list[dict[str, Any]],
    *,
    runtime: dict[str, Any],
    monitor: dict[str, Any],
) -> None:
    monitor_started = bool(runtime.get("monitor_started"))
    if not monitor_started:
        return

    if not bool(monitor.get("running")):
        _add_issue(
            issues,
            "critical",
            "tiktok_monitor_stopped",
            "Monitor do TikTok nao esta rodando.",
        )
        return

    if not bool(monitor.get("listening")):
        _add_issue(
            issues,
            "critical",
            "tiktok_monitor_not_listening",
            "Monitor do TikTok nao esta escutando eventos.",
        )

    if not bool(monitor.get("connected")):
        _add_issue(
            issues,
            "warning",
            "tiktok_monitor_disconnected",
            "Monitor do TikTok esta rodando, mas ainda nao conectou na live.",
        )


def _check_audio(
    issues: list[dict[str, Any]],
    *,
    now: float,
    metrics: dict[str, Any],
    speech: dict[str, Any],
) -> None:
    audio = _dict(metrics.get("audio"))
    if not audio:
        _add_issue(
            issues,
            "warning",
            "audio_metrics_missing",
            "Metricas de audio ainda nao apareceram.",
        )
        return

    if _int(audio.get("rate")) not in {0, 48000}:
        _add_issue(
            issues,
            "warning",
            "audio_rate_unexpected",
            "Taxa de audio diferente de 48 kHz.",
            {"rate": _int(audio.get("rate"))},
        )

    if _int(audio.get("aac_bitrate")) not in {0, 160000}:
        _add_issue(
            issues,
            "warning",
            "audio_bitrate_unexpected",
            "Bitrate AAC diferente de 160 kbps.",
            {"aac_bitrate": _int(audio.get("aac_bitrate"))},
        )

    audio_age = _age(now, audio.get("updated_at"))
    if audio_age >= AUDIO_STALE_SECONDS:
        _add_issue(
            issues,
            "warning",
            "audio_level_stale",
            "Nivel de audio parou de atualizar.",
            {"age_seconds": round(audio_age, 1)},
        )

    rms_values = _float_list(audio.get("rms"))
    peak_values = _float_list(audio.get("peak"))
    if rms_values:
        average_rms = sum(rms_values) / len(rms_values)
        voice_or_song_active = bool(
            speech.get("active")
            or song_runtime.singing_active()
        )
        if voice_or_song_active and average_rms <= -55.0:
            _add_issue(
                issues,
                "warning",
                "audio_very_low",
                "Audio muito baixo durante fala/canto ativo.",
                {"rms_db": round(average_rms, 1)},
            )

    if peak_values and max(peak_values) >= -0.2:
        _add_issue(
            issues,
            "warning",
            "audio_peak_hot",
            "Audio chegando perto de clipar.",
            {"peak_db": round(max(peak_values), 2)},
        )


def _check_rtmp(
    issues: list[dict[str, Any]],
    *,
    metrics: dict[str, Any],
) -> None:
    if not bool(metrics.get("rtmp_url_present")):
        _add_issue(
            issues,
            "critical",
            "rtmp_url_missing",
            "Captura ativa sem URL RTMP.",
        )
        return

    rtmp = _dict(metrics.get("rtmp"))
    if not rtmp:
        _add_issue(
            issues,
            "critical",
            "rtmp_metrics_missing",
            "Metricas RTMP nao apareceram.",
        )
        return

    if not bool(rtmp.get("has_stats")):
        _add_issue(
            issues,
            "warning",
            "rtmp_stats_unavailable",
            "Sink RTMP nao expos estatisticas.",
        )
        return

    out_total = _int(rtmp.get("out_total"))
    out_acked = _int(rtmp.get("out_acked"))
    unacked = _int(rtmp.get("unacked"))
    no_ack_seconds = _float(rtmp.get("no_ack_seconds"))
    stale_ack_seconds = _float(rtmp.get("stale_ack_seconds"))

    if (
        out_total >= RTMP_NO_ACK_MIN_BYTES
        and out_acked <= 0
        and no_ack_seconds >= RTMP_NO_ACK_SECONDS
    ):
        _add_issue(
            issues,
            "info",
            "rtmp_no_ack",
            "RTMP sem ACK local; se o TikTok esta recebendo, manter a live sem reiniciar.",
            {"out_total": out_total, "out_acked": out_acked},
        )
    elif (
        out_total >= RTMP_STALE_ACK_MIN_BYTES
        and out_acked > 0
        and unacked > 0
        and stale_ack_seconds >= RTMP_STALE_ACK_SECONDS
    ):
        _add_issue(
            issues,
            "critical",
            "rtmp_ack_stale",
            "ACK do RTMP parou de avancar.",
            {
                "out_total": out_total,
                "out_acked": out_acked,
                "unacked": unacked,
            },
        )


def _check_queues(
    issues: list[dict[str, Any]],
    *,
    metrics: dict[str, Any],
) -> None:
    queues = _dict(metrics.get("queues"))
    for name, raw_queue in queues.items():
        queue = _dict(raw_queue)
        queued_ms = _float(queue.get("ms"))
        if queued_ms >= 1500.0:
            _add_issue(
                issues,
                "warning",
                "pipeline_queue_delay",
                "Fila do pipeline esta acumulando latencia.",
                {
                    "queue": str(name),
                    "ms": round(queued_ms, 1),
                },
            )


def _components(
    *,
    runtime: dict[str, Any],
    metrics: dict[str, Any],
    metrics_age: float,
    capture_pid: int,
    capture_alive: bool,
    godot: dict[str, Any],
    speech: dict[str, Any],
    monitor: dict[str, Any],
) -> dict[str, Any]:
    audio = _dict(metrics.get("audio"))
    rtmp = _dict(metrics.get("rtmp"))
    return {
        "runtime": {
            "state": str(runtime.get("state") or "stopped"),
            "session_id": str(runtime.get("session_id") or ""),
            "monitor_started": bool(runtime.get("monitor_started")),
            "destination_ready": bool(runtime.get("destination_ready")),
            "last_error": str(runtime.get("last_error") or ""),
        },
        "capture": {
            "pid": capture_pid,
            "alive": capture_alive,
            "metrics_age_seconds": round(metrics_age, 1),
            "rtmp_url_present": bool(metrics.get("rtmp_url_present")),
        },
        "godot": {
            "connected": bool(godot.get("connected")),
            "last_message_at": _float(godot.get("last_message_at")),
        },
        "speech": {
            "dispatcher_running": dispatcher_running(),
            "pending_size": _int(speech.get("pending_size")),
            "ready_size": _int(speech.get("ready_size")),
            "active": bool(speech.get("active")),
        },
        "monitor": {
            "running": bool(monitor.get("running")),
            "connected": bool(monitor.get("connected")),
            "listening": bool(monitor.get("listening")),
            "last_error": str(monitor.get("last_error") or ""),
        },
        "audio": {
            "rate": _int(audio.get("rate")),
            "channels": _int(audio.get("channels")),
            "aac_bitrate": _int(audio.get("aac_bitrate")),
            "level_updated_at": _float(audio.get("updated_at")),
            "dynamics": _dict(audio.get("dynamics")),
        },
        "rtmp": {
            "sink": str(rtmp.get("sink") or ""),
            "has_stats": bool(rtmp.get("has_stats")),
            "out_total": _int(rtmp.get("out_total")),
            "out_acked": _int(rtmp.get("out_acked")),
            "unacked": _int(rtmp.get("unacked")),
            "no_ack_seconds": _float(rtmp.get("no_ack_seconds")),
            "stale_ack_seconds": _float(rtmp.get("stale_ack_seconds")),
        },
    }


def _add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    issue: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    if details:
        issue["details"] = dict(details)
    issues.append(issue)


def _overall_status(issues: list[dict[str, Any]]) -> str:
    severities = {
        str(item.get("severity") or "")
        for item in issues
        if isinstance(item, dict)
    }
    if "critical" in severities:
        return "critical"
    if "warning" in severities:
        return "warning"
    return "ok"


def _actions_for(issues: list[dict[str, Any]]) -> list[str]:
    codes = {
        str(item.get("code") or "")
        for item in issues
        if isinstance(item, dict)
    }
    actions: list[str] = []
    if "capture_process_dead" in codes or "output_metrics_stale" in codes:
        actions.append("Reiniciar somente a captura local mantendo a mesma URL/chave RTMP.")
    if "godot_disconnected" in codes or "godot_heartbeat_stale" in codes:
        actions.append("Reabrir/validar a janela do jogo e a conexao WebSocket da cobrinha.")
    if "speech_dispatcher_stopped" in codes or "speech_active_stale" in codes:
        actions.append("Limpar fala ativa travada e reiniciar o despachador de fala.")
    if "tiktok_monitor_stopped" in codes or "tiktok_monitor_not_listening" in codes:
        actions.append("Reiniciar o monitor TikTok local sem reiniciar a live.")
    if "rtmp_no_ack" in codes:
        actions.append("Manter a mesma URL/chave; nao reiniciar a live apenas por falta de ACK local.")
    if "rtmp_ack_stale" in codes:
        actions.append("Verificar conexao RTMP; nao gerar nova chave automaticamente.")
    return actions


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float_list(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    result: list[float] = []
    for item in value:
        number = _float(item)
        result.append(number)
    return result


def _age(
    now: float,
    timestamp: object,
) -> float:
    value = _float(timestamp)
    if value <= 0.0:
        return 999999.0
    return max(0.0, now - value)


def _int(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
