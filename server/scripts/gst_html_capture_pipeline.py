#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gst  # noqa: E402


WIDTH = 720
HEIGHT = 1280
FPS = 30
AUDIO_RATE = 48000
AUDIO_BITRATE = 160000


def main() -> None:
    args = parse_args()
    Gst.init(None)
    attempts = 0
    args.active_rtmp_sink = choose_rtmp_sink(args.rtmp_sink, args.rtmp_url)
    args.auto_sink_fallback_used = False
    while True:
        error, stopped = run_pipeline(args)
        if stopped or not error:
            return
        if maybe_fallback_rtmp_sink(args):
            attempts = 0
            continue
        if not should_retry_rtmp(args, attempts):
            raise SystemExit(1)
        attempts += 1
        print(
            f"[html-capture] RTMP remoto fechou a conexao; "
            f"reiniciando captura {attempts}/{args.rtmp_restart_max} "
            f"sink={current_rtmp_sink(args)} {rtmp_destination_label(args.rtmp_url)}",
            file=sys.stderr,
            flush=True,
        )
        delay = max(0.0, float(args.rtmp_restart_delay_seconds or 0.0))
        if delay:
            time.sleep(delay)


def run_pipeline(args: argparse.Namespace) -> tuple[bool, bool]:
    if args.rtmp_url and not args.output_file:
        print(
            f"[html-capture] destino RTMP sink={current_rtmp_sink(args)} "
            f"{rtmp_destination_label(args.rtmp_url)}",
            file=sys.stderr,
            flush=True,
        )
    pipeline = Gst.parse_launch(build_pipeline(args))
    if not isinstance(pipeline, Gst.Pipeline):
        raise RuntimeError("Falha ao criar pipeline GStreamer.")

    loop = GLib.MainLoop()
    state = {
        "error": False,
        "done": False,
        "stopping": False,
        "loop": loop,
        "rtmp_url": str(args.rtmp_url or ""),
    }
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_bus_message, loop, state)

    def stop(_signum: int, _frame: object) -> None:
        state["stopping"] = True
        loop.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    install_timestamp_probes(pipeline, state)
    pipeline.set_state(Gst.State.PLAYING)
    install_pipeline_diagnostics(pipeline, state, args)
    try:
        loop.run()
    finally:
        state["done"] = True
        try:
            bus.remove_signal_watch()
        except Exception:
            pass
        pipeline.set_state(Gst.State.NULL)
    return bool(state.get("error")), bool(state.get("stopping"))



def install_timestamp_probes(
    pipeline: Gst.Pipeline,
    state: dict[str, object],
) -> None:
    snapshots: dict[str, dict[str, int]] = {}
    state["timestamp_diag"] = snapshots

    def attach(label: str, element_name: str) -> None:
        element = pipeline.get_by_name(element_name)

        if element is None:
            raise RuntimeError(
                f"elemento de diagnostico ausente: {element_name}"
            )

        pad = element.get_static_pad("src")

        if pad is None:
            raise RuntimeError(
                f"src pad ausente: {element_name}"
            )

        snapshots[label] = {
            "count": 0,
            "first_pts": -1,
            "last_pts": -1,
            "last_dts": -1,
            "last_duration": -1,
        }

        def probe(_pad, info):
            buffer = info.get_buffer()

            if buffer is None:
                return Gst.PadProbeReturn.OK

            snap = snapshots[label]

            pts = (
                int(buffer.pts)
                if buffer.pts != Gst.CLOCK_TIME_NONE
                else -1
            )

            dts = (
                int(buffer.dts)
                if buffer.dts != Gst.CLOCK_TIME_NONE
                else -1
            )

            duration = (
                int(buffer.duration)
                if buffer.duration != Gst.CLOCK_TIME_NONE
                else -1
            )

            snap["count"] += 1

            if snap["first_pts"] < 0 and pts >= 0:
                snap["first_pts"] = pts

            snap["last_pts"] = pts
            snap["last_dts"] = dts
            snap["last_duration"] = duration

            return Gst.PadProbeReturn.OK

        pad.add_probe(
            Gst.PadProbeType.BUFFER,
            probe,
        )

    attach("aac", "html_audio_parse")
    attach("h264", "html_video_parse")
    attach("flv", "mux")


def install_pipeline_diagnostics(
    pipeline: Gst.Pipeline,
    state: dict[str, object],
    args: argparse.Namespace,
) -> None:
    selected_rtmp_sink = current_rtmp_sink(args)
    state["clock_logged"] = False
    state["rtmp_first_stat_at"] = 0.0
    state["rtmp_last_ack_at"] = 0.0
    state["started_at"] = time.time()

    def tick() -> bool:
        if state.get("stopping") or state.get("done"):
            return False

        clock = pipeline.get_clock()
        clock_name = clock.get_name() if clock is not None else "none"

        if not state.get("clock_logged"):
            state["clock_logged"] = True
            print(
                f"[html-capture] pipeline clock={clock_name} base_time={pipeline.get_base_time()}",
                file=sys.stderr,
                flush=True,
            )

        audio_src = pipeline.get_by_name("html_audio_src")
        audio_rate = pipeline.get_by_name("html_audio_rate")

        def prop_int(element, name: str) -> int:
            if element is None:
                return -1
            try:
                return int(element.get_property(name))
            except Exception:
                return -1

        try:
            base_ns = int(pipeline.get_base_time())
        except Exception:
            base_ns = 0

        try:
            clock_ns = int(clock.get_time()) if clock is not None else 0
        except Exception:
            clock_ns = 0

        running_ns = (
            clock_ns - base_ns
            if base_ns > 0 and clock_ns >= base_ns
            else 0
        )

        def caps_text(element, pad_name: str) -> str:
            if element is None:
                return "missing"

            pad = element.get_static_pad(pad_name)

            if pad is None:
                return "no-pad"

            try:
                caps = pad.get_current_caps()
            except Exception:
                return "error"

            if caps is None:
                return "none"

            try:
                return caps.to_string()
            except Exception:
                return "error"

        print(
            "[html-capture] timing "
            f"clock={clock_name} "
            f"base_ns={base_ns} "
            f"clock_ns={clock_ns} "
            f"running_ns={running_ns} "
            f"rate_in={prop_int(audio_rate, 'in')} "
            f"rate_out={prop_int(audio_rate, 'out')} "
            f"rate_add={prop_int(audio_rate, 'add')} "
            f"rate_drop={prop_int(audio_rate, 'drop')} "
            f"buffer_us={prop_int(audio_src, 'actual-buffer-time')} "
            f"latency_us={prop_int(audio_src, 'actual-latency-time')} "
            f"rate_in_caps={caps_text(audio_rate, 'sink')!r} "
            f"rate_out_caps={caps_text(audio_rate, 'src')!r}",
            file=sys.stderr,
            flush=True,
        )

        queue_parts: list[str] = []
        queue_metrics: dict[str, dict[str, float | int]] = {}
        for name in (
            "video_in_q",
            "video_post_comp_q",
            "audio_in_q",
            "audio_mux_q",
            "rtmp_out_q",
            "file_out_q",
        ):
            element = pipeline.get_by_name(name)
            if element is None:
                continue
            try:
                buffers = int(element.get_property("current-level-buffers"))
                level_time = int(element.get_property("current-level-time"))
            except Exception:
                continue
            queue_metrics[name] = {
                "buffers": buffers,
                "ms": round(level_time / 1_000_000, 3),
            }
            queue_parts.append(
                f"{name}:buffers={buffers},ms={level_time / 1_000_000:.1f}"
            )

        if queue_parts:
            print(
                "[html-capture] queues " + " | ".join(queue_parts),
                file=sys.stderr,
                flush=True,
            )

        rtmp_metrics: dict[str, object] = {
            "sink": selected_rtmp_sink,
            "has_stats": False,
        }
        rtmp_sink = pipeline.get_by_name("html_rtmp_sink")
        if rtmp_sink is not None:
            try:
                stats = rtmp_sink.get_property("stats")
            except Exception:
                stats = None

            if stats is not None:
                def stat_int(name: str) -> int:
                    try:
                        return int(stats.get_value(name))
                    except Exception:
                        return -1

                if selected_rtmp_sink != "rtmp2sink":
                    rtmp_metrics = {
                        "sink": selected_rtmp_sink,
                        "has_stats": True,
                    }
                else:
                    out_total = stat_int("out-bytes-total")
                    out_acked = stat_int("out-bytes-acked")
                    unacked = (
                        out_total - out_acked
                        if out_total >= 0 and out_acked >= 0
                        else -1
                    )
                    now = time.monotonic()
                    if not state.get("rtmp_first_stat_at"):
                        state["rtmp_first_stat_at"] = now
                    if out_acked > 0:
                        state["rtmp_last_ack_at"] = now
                    first_stat_at = float(state.get("rtmp_first_stat_at") or now)
                    last_ack_at = float(state.get("rtmp_last_ack_at") or 0.0)
                    rtmp_metrics = {
                        "sink": selected_rtmp_sink,
                        "has_stats": True,
                        "out_total": out_total,
                        "out_acked": out_acked,
                        "unacked": unacked,
                        "no_ack_seconds": (
                            round(now - first_stat_at, 1)
                            if out_acked <= 0
                            else 0.0
                        ),
                        "stale_ack_seconds": (
                            round(now - last_ack_at, 1)
                            if last_ack_at > 0
                            else 0.0
                        ),
                        "in_chunk": stat_int("in-chunk-size"),
                        "out_chunk": stat_int("out-chunk-size"),
                        "in_window_ack": stat_int("in-window-ack-size"),
                        "out_window_ack": stat_int("out-window-ack-size"),
                    }
                    print(
                        "[html-capture] rtmp2sink "
                        f"out_total={out_total} "
                        f"out_acked={out_acked} "
                        f"unacked={unacked} "
                        f"in_chunk={stat_int('in-chunk-size')} "
                        f"out_chunk={stat_int('out-chunk-size')} "
                        f"in_window_ack={stat_int('in-window-ack-size')} "
                        f"out_window_ack={stat_int('out-window-ack-size')}",
                        file=sys.stderr,
                        flush=True,
                    )
                    if not warn_for_rtmp_ack_lag(args, state, out_total, out_acked, unacked, now):
                        return False

        timestamp_diag = state.get("timestamp_diag") or {}
        timestamp_parts: list[str] = []

        for label in ("aac", "h264", "flv"):
            snap = timestamp_diag.get(label) or {}

            first_pts = int(snap.get("first_pts", -1))
            last_pts = int(snap.get("last_pts", -1))

            delta_pts = (
                last_pts - first_pts
                if first_pts >= 0 and last_pts >= first_pts
                else -1
            )

            timestamp_parts.append(
                f"{label}:"
                f"count={int(snap.get('count', 0))},"
                f"pts_ns={last_pts},"
                f"delta_ns={delta_pts},"
                f"dts_ns={int(snap.get('last_dts', -1))},"
                f"dur_ns={int(snap.get('last_duration', -1))}"
            )
            rtmp_metrics.setdefault("pts", {})
            if isinstance(rtmp_metrics["pts"], dict):
                rtmp_metrics["pts"][label] = {
                    "count": int(snap.get("count", 0)),
                    "pts_ns": last_pts,
                    "delta_ns": delta_pts,
                    "duration_ns": int(snap.get("last_duration", -1)),
                }

        print(
            "[html-capture] pts "
            + " | ".join(timestamp_parts),
            file=sys.stderr,
            flush=True,
        )
        write_metrics(args, state, queue_metrics, rtmp_metrics, clock_name)

        return True

    interval = max(1, int(float(args.diagnostic_interval_seconds or 5)))
    GLib.timeout_add_seconds(interval, tick)


def write_metrics(
    args: argparse.Namespace,
    state: dict[str, object],
    queues: dict[str, dict[str, float | int]],
    rtmp: dict[str, object],
    clock_name: str,
) -> None:
    path_text = str(args.metrics_file or "").strip()
    if not path_text:
        return
    path = Path(path_text)
    payload = {
        "updated_at": time.time(),
        "pid": os.getpid(),
        "started_at": float(state.get("started_at") or 0.0),
        "display": str(args.display or ""),
        "capture": {
            "x": int(args.capture_x or 0),
            "y": int(args.capture_y or 0),
            "width": int(args.capture_width or 0),
            "height": int(args.capture_height or 0),
        },
        "output": {
            "width": output_width(args),
            "height": output_height(args),
            "fps": output_fps(args),
            "video_bitrate_kbps": max(300, min(12000, int(args.video_bitrate))),
        },
        "audio_source": str(args.audio_source or ""),
        "audio": {
            "rms": state.get("audio_rms") or [],
            "peak": state.get("audio_peak") or [],
            "updated_at": float(state.get("audio_level_updated_at") or 0.0),
            "rate": output_audio_rate(args),
            "channels": 2,
            "aac_bitrate": output_audio_bitrate(args),
            "dynamics": {
                "enabled": (
                    not bool(getattr(args, "disable_audio_dynamics", False))
                    and audio_dynamics_available()
                ),
                "available": audio_dynamics_available(),
                "compressor": "audiodynamic",
                "threshold": 0.82,
                "ratio": 3.0,
                "limiter_gain": 0.95,
            },
        },
        "output_file": str(args.output_file or ""),
        "rtmp_url_present": bool(str(args.rtmp_url or "").strip()),
        "rtmp_fingerprint": rtmp_url_fingerprint(args.rtmp_url),
        "clock": clock_name,
        "queues": queues,
        "rtmp": rtmp,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def warn_for_rtmp_ack_lag(
    args: argparse.Namespace,
    state: dict[str, object],
    out_total: int,
    out_acked: int,
    unacked: int,
    now: float,
) -> bool:
    if args.output_file or not args.rtmp_url:
        return True
    if out_total < 0 or out_acked < 0 or unacked < 0:
        return True

    first_stat_at = float(state.get("rtmp_first_stat_at") or now)
    last_ack_at = float(state.get("rtmp_last_ack_at") or 0.0)
    no_ack_timeout = max(0.0, float(args.rtmp_no_ack_timeout or 0.0))
    stale_ack_timeout = max(0.0, float(args.rtmp_stale_ack_timeout or 0.0))
    min_bytes = max(0, int(args.rtmp_no_ack_min_bytes or 0))
    stale_min_bytes = max(min_bytes, int(args.rtmp_stale_ack_min_bytes or 0))
    warning_interval = max(10.0, float(args.rtmp_ack_warning_interval or 30.0))

    def should_warn(key: str) -> bool:
        previous = float(state.get(key) or 0.0)
        if previous and now - previous < warning_interval:
            return False
        state[key] = now
        return True

    def abort_for_bad_ack(reason: str) -> bool:
        if not bool(args.rtmp_fail_on_ack_lag):
            return True
        state["error"] = True
        state["done"] = True
        print(
            f"[html-capture] erro RTMP: {reason}; reiniciando captura para nao manter live bugada",
            file=sys.stderr,
            flush=True,
        )
        loop = state.get("loop")
        if loop is not None:
            try:
                loop.quit()
            except Exception:
                pass
        return False

    if (
        no_ack_timeout
        and out_acked <= 0
        and out_total >= min_bytes
        and now - first_stat_at >= no_ack_timeout
    ):
        if should_warn("rtmp_no_ack_warning_at"):
            print(
                "[html-capture] aviso RTMP: stats sem ACK do servidor "
                f"ha {now - first_stat_at:.1f}s "
                f"out_total={out_total} unacked={unacked}",
                file=sys.stderr,
                flush=True,
            )
        return abort_for_bad_ack(
            f"servidor sem ACK ha {now - first_stat_at:.1f}s "
            f"out_total={out_total} unacked={unacked}"
        )

    if (
        stale_ack_timeout
        and last_ack_at > 0
        and unacked >= stale_min_bytes
        and now - last_ack_at >= stale_ack_timeout
    ):
        if should_warn("rtmp_stale_ack_warning_at"):
            print(
                "[html-capture] aviso RTMP: stats com ACK parado "
                f"ha {now - last_ack_at:.1f}s "
                f"out_total={out_total} out_acked={out_acked} unacked={unacked}",
                file=sys.stderr,
                flush=True,
            )
        return abort_for_bad_ack(
            f"ACK parado ha {now - last_ack_at:.1f}s "
            f"out_total={out_total} out_acked={out_acked} unacked={unacked}"
        )

    return True

def build_pipeline(args: argparse.Namespace) -> str:
    bitrate = max(300, min(12000, int(args.video_bitrate)))
    audio_rate = output_audio_rate(args)
    audio_bitrate = output_audio_bitrate(args)
    print(
        "[html-capture] output="
        f"{output_width(args)}x{output_height(args)}@{output_fps(args)} "
        f"bitrate={bitrate}kbps "
        f"audio={audio_rate}Hz/{audio_bitrate}bps",
        file=sys.stderr,
        flush=True,
    )
    return " ".join([
        *video_branch(args, bitrate),
        *audio_branch(args),
        *output_branch(args),
    ])


def video_branch(args: argparse.Namespace, bitrate: int) -> list[str]:
    width = output_width(args)
    height = output_height(args)
    fps = output_fps(args)
    return [
        "ximagesrc",
        f"display-name={gst_quote(args.display)}",
        *window_xid_props(args),
        *capture_region_props(args),
        "remote=true",
        "use-damage=false",
        "show-pointer=false",
        "do-timestamp=true",
        "!",
        "videorate",
        "!",
        f"video/x-raw,framerate={fps}/1",
        "!",
        "queue",
        "name=video_in_q",
        "leaky=downstream",
        "max-size-buffers=2",
        "!",
        "videoconvert",
        "!",
        "videoscale",
        "!",
        f"video/x-raw,width={width},height={height},format=BGRA",
        "!",
        "compositor",
        "name=comp",
        "force-live=true",
        "ignore-inactive-pads=true",
        "background=black",
        "sink_0::xpos=0",
        "sink_0::ypos=0",
        "sink_0::zorder=0",
        "!",
        "queue",
        "name=video_post_comp_q",
        "leaky=downstream",
        "max-size-buffers=2",
        "max-size-time=0",
        "max-size-bytes=0",
        "!",
        "videoconvert",
        "!",
        "queue",
        "leaky=downstream",
        "max-size-buffers=2",
        "max-size-time=0",
        "max-size-bytes=0",
        "!",
        *encoder_branch(args, bitrate),
        "h264parse",
        "name=html_video_parse",
        "config-interval=1",
        "!",
        "queue",
        "!",
        "mux.",
    ]


def capture_region_props(args: argparse.Namespace) -> list[str]:
    width = max(0, int(args.capture_width or 0))
    height = max(0, int(args.capture_height or 0))
    if width <= 0 or height <= 0:
        return []
    start_x = int(args.capture_x or 0)
    start_y = int(args.capture_y or 0)
    return [
        f"startx={start_x}",
        f"starty={start_y}",
        f"endx={start_x + width - 1}",
        f"endy={start_y + height - 1}",
    ]


def window_xid_props(args: argparse.Namespace) -> list[str]:
    xid = max(0, int(args.window_xid or 0))
    if xid <= 0:
        return []
    return [
        f"xid={xid}",
    ]


def encoder_branch(args: argparse.Namespace, bitrate: int) -> list[str]:
    requested = str(args.video_encoder or "x264").lower().strip()
    width = output_width(args)
    height = output_height(args)
    fps = output_fps(args)
    if requested == "nvenc" and Gst.ElementFactory.find("nvh264enc") is not None:
        print("[html-capture] video encoder=nvh264enc", file=sys.stderr, flush=True)
        return [
            f"video/x-raw,format=NV12,width={width},height={height},framerate={fps}/1",
            "!",
            "nvh264enc",
            f"bitrate={bitrate}",
            f"gop-size={fps * 2}",
            "preset=low-latency-hp",
            "rc-mode=cbr",
            "zerolatency=true",
            "bframes=0",
            "!",
        ]
    print("[html-capture] video encoder=x264enc", file=sys.stderr, flush=True)
    return [
        f"video/x-raw,format=I420,width={width},height={height},framerate={fps}/1",
        "!",
        "x264enc",
        "tune=zerolatency",
        "speed-preset=ultrafast",
        "threads=0",
        "sliced-threads=true",
        "bframes=0",
        "byte-stream=true",
        f"bitrate={bitrate}",
        f"key-int-max={fps * 2}",
        "!",
    ]


def output_width(args: argparse.Namespace) -> int:
    return max(320, min(3840, int(args.output_width or WIDTH)))


def output_height(args: argparse.Namespace) -> int:
    return max(320, min(3840, int(args.output_height or HEIGHT)))


def output_fps(args: argparse.Namespace) -> int:
    return max(1, min(120, int(args.fps or FPS)))


def output_audio_rate(args: argparse.Namespace) -> int:
    return max(8000, min(96000, int(args.audio_rate or AUDIO_RATE)))


def output_audio_bitrate(args: argparse.Namespace) -> int:
    return max(64000, min(320000, int(args.audio_bitrate or AUDIO_BITRATE)))


def audio_branch(args: argparse.Namespace) -> list[str]:
    if not args.audio_source:
        raise RuntimeError("audio-source vazio; informe uma fonte .monitor para evitar capturar microfone.")
    audio_rate = output_audio_rate(args)
    audio_bitrate = output_audio_bitrate(args)
    level_interval_ns = int(
        max(1.0, float(args.diagnostic_interval_seconds or 5.0))
        * 1_000_000_000
    )
    return [
        "pulsesrc",
        "name=html_audio_src",
        "do-timestamp=true",
        f"device={gst_quote(args.audio_source)}",
        "!",
        "queue",
        "name=audio_in_q",
        "max-size-buffers=0",
        "max-size-bytes=0",
        "max-size-time=2000000000",
        "!",
        "audioconvert",
        "!",
        "audioresample",
        "!",
        "audiorate",
        "name=html_audio_rate",
        "skip-to-first=true",
        "!",
        f"audio/x-raw,rate={audio_rate},channels=2",
        "!",
        *audio_dynamics_branch(args),
        "level",
        "name=html_audio_level",
        f"interval={level_interval_ns}",
        "message=true",
        "!",
        "avenc_aac",
        "name=html_aac_enc",
        f"bitrate={audio_bitrate}",
        "!",
        "aacparse",
        "name=html_audio_parse",
        "!",
        "queue",
        "name=audio_mux_q",
        "max-size-buffers=0",
        "max-size-bytes=0",
        "max-size-time=2000000000",
        "!",
        "mux.",
    ]


def audio_dynamics_branch(args: argparse.Namespace) -> list[str]:
    if not audio_dynamics_enabled(args):
        return []
    audio_rate = output_audio_rate(args)

    print(
        "[html-capture] audio compressor=audiodynamic soft-knee",
        file=sys.stderr,
        flush=True,
    )
    return [
        "audioconvert",
        "!",
        f"audio/x-raw,format=F32LE,rate={audio_rate},channels=2",
        "!",
        "audiodynamic",
        "name=html_audio_compressor",
        "mode=compressor",
        "characteristics=soft-knee",
        "threshold=0.82",
        "ratio=3.0",
        "!",
        "audioamplify",
        "name=html_audio_limiter",
        "amplification=0.95",
        "clipping-method=clip",
        "!",
        "audioconvert",
        "!",
        f"audio/x-raw,rate={audio_rate},channels=2",
        "!",
    ]


def audio_dynamics_enabled(args: argparse.Namespace) -> bool:
    if bool(getattr(args, "disable_audio_dynamics", False)):
        return False
    if not audio_dynamics_available():
        print(
            "[html-capture] audio compressor indisponivel; usando audio direto",
            file=sys.stderr,
            flush=True,
        )
        return False
    return True


def audio_dynamics_available() -> bool:
    return (
        Gst.ElementFactory.find("audiodynamic") is not None
        and Gst.ElementFactory.find("audioamplify") is not None
    )


def output_branch(args: argparse.Namespace) -> list[str]:
    base = ["flvmux", "name=mux", "streamable=true", "!"]
    if args.output_file:
        return [
            *base,
            "queue",
            "name=file_out_q",
            "max-size-buffers=0",
            "max-size-bytes=0",
            "max-size-time=2000000000",
            "!",
            "filesink",
            f"location={gst_quote(args.output_file)}",
            "sync=true",
        ]
    if not args.rtmp_url:
        raise RuntimeError("rtmp-url vazio e output-file vazio.")
    sink = current_rtmp_sink(args)
    sink_props = [
        "name=html_rtmp_sink",
        f"location={gst_quote(args.rtmp_url)}",
        "sync=true",
        "async=false",
    ]
    return [
        *base,
        "queue",
        "name=rtmp_out_q",
        "leaky=downstream",
        "max-size-buffers=8",
        "max-size-time=0",
        "max-size-bytes=0",
        "!",
        sink,
        *sink_props,
    ]


def choose_rtmp_sink(requested: object, rtmp_url: object) -> str:
    clean = str(requested or "auto").strip().lower()
    if clean in {"rtmpsink", "rtmp2sink"}:
        return clean
    url = str(rtmp_url or "").strip().lower()
    if url.startswith("rtmps://") and not is_tiktok_rtmp_url(url):
        return "rtmpsink"
    return "rtmp2sink"


def is_tiktok_rtmp_url(rtmp_url: object) -> bool:
    text = str(rtmp_url or "").strip().lower()
    if not text:
        return False
    try:
        host = urlsplit(text).netloc.lower()
    except ValueError:
        return "tiktok" in text
    return "tiktok" in host or "tiktokcdn" in host


def current_rtmp_sink(args: argparse.Namespace) -> str:
    active = str(getattr(args, "active_rtmp_sink", "") or "").strip().lower()
    if active in {"rtmpsink", "rtmp2sink"}:
        return active
    return choose_rtmp_sink(args.rtmp_sink, args.rtmp_url)


def maybe_fallback_rtmp_sink(args: argparse.Namespace) -> bool:
    if args.output_file or not args.rtmp_url:
        return False
    if str(args.rtmp_sink or "").strip().lower() != "auto":
        return False
    if bool(getattr(args, "auto_sink_fallback_used", False)):
        return False
    if current_rtmp_sink(args) != "rtmpsink":
        return False
    args.active_rtmp_sink = "rtmp2sink"
    args.auto_sink_fallback_used = True
    print(
        "[html-capture] rtmpsink falhou; alternando para rtmp2sink "
        f"sem encerrar a sessao {rtmp_destination_label(args.rtmp_url)}",
        file=sys.stderr,
        flush=True,
    )
    return True


def rtmp_url_fingerprint(rtmp_url: object) -> str:
    text = str(rtmp_url or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def rtmp_destination_label(rtmp_url: object) -> str:
    text = str(rtmp_url or "").strip()
    if not text:
        return "destination=none"
    fingerprint = rtmp_url_fingerprint(text)
    try:
        parsed = urlsplit(text)
    except ValueError:
        return f"destination=rtmp:fp={fingerprint}"
    path_parts = [part for part in parsed.path.split("/") if part]
    app = path_parts[0] if path_parts else ""
    return (
        f"destination=rtmp:host={parsed.netloc or '-'} "
        f"app={app or '-'} fp={fingerprint}"
    )


def redact_sensitive_text(value: object, rtmp_url: object = "") -> str:
    text = str(value or "")
    url = str(rtmp_url or "").strip()
    if url:
        text = text.replace(url, f"[{rtmp_destination_label(url)}]")
    text = re.sub(r"rtmps?://[^\s\"']+", "[rtmp-url-redacted]", text)
    text = re.sub(r"stream-\d+[^\s\"']*", "stream-[redacted]", text)
    text = re.sub(r"(wsSecret=)[^&\s\"']+", r"\1[redacted]", text)
    return re.sub(r"(wsTime=)[^&\s\"']+", r"\1[redacted]", text)


def on_bus_message(_bus: Gst.Bus, message: Gst.Message, loop: GLib.MainLoop, state: dict[str, object]) -> None:
    if message.type == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        state["error"] = True
        state["done"] = True
        detail = redact_sensitive_text(
            f"{err} {debug or ''}",
            state.get("rtmp_url") or "",
        )
        print(f"[html-capture] erro GStreamer: {detail}", file=sys.stderr, flush=True)
        loop.quit()
    elif message.type == Gst.MessageType.EOS:
        state["done"] = True
        loop.quit()
    elif message.type == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        detail = redact_sensitive_text(
            f"{err} {debug or ''}",
            state.get("rtmp_url") or "",
        )
        print(f"[html-capture] aviso GStreamer: {detail}", file=sys.stderr, flush=True)
    elif message.type == Gst.MessageType.QOS:
        try:
            live, running_time, stream_time, timestamp, duration = message.parse_qos()
            print(
                f"[html-capture] QOS live={live} running={running_time} stream={stream_time} ts={timestamp} duration={duration}",
                file=sys.stderr,
                flush=True,
            )
        except Exception as exc:
            print(f"[html-capture] QOS parse failed: {exc}", file=sys.stderr, flush=True)
    elif message.type == Gst.MessageType.ELEMENT:
        structure = message.get_structure()
        if structure is not None and structure.get_name() == "level":
            rms = structure.get_value("rms")
            peak = structure.get_value("peak")
            state["audio_rms"] = numeric_list(rms)
            state["audio_peak"] = numeric_list(peak)
            state["audio_level_updated_at"] = time.time()
            print(f"[html-capture] audio level rms={rms} peak={peak}", file=sys.stderr, flush=True)


def numeric_list(value: object) -> list[float]:
    result: list[float] = []
    try:
        for item in value:  # type: ignore[operator]
            try:
                result.append(float(item))
            except (TypeError, ValueError):
                continue
    except TypeError:
        try:
            result.append(float(value))
        except (TypeError, ValueError):
            pass
    return result


def should_retry_rtmp(args: argparse.Namespace, attempts: int) -> bool:
    if attempts >= max(0, int(args.rtmp_restart_max)):
        return False
    if args.output_file:
        return False
    return bool(str(args.rtmp_url or "").strip())


def gst_quote(value: object) -> str:
    text = str(value or "")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Captura renderer para RTMP/arquivo.")
    parser.add_argument("--display", required=True)
    parser.add_argument("--capture-x", type=int, default=0)
    parser.add_argument("--capture-y", type=int, default=0)
    parser.add_argument("--capture-width", type=int, default=0)
    parser.add_argument("--capture-height", type=int, default=0)
    parser.add_argument("--output-width", type=int, default=WIDTH)
    parser.add_argument("--output-height", type=int, default=HEIGHT)
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--audio-rate", type=int, default=AUDIO_RATE)
    parser.add_argument("--audio-bitrate", type=int, default=AUDIO_BITRATE)
    parser.add_argument("--window-xid", type=int, default=0)
    parser.add_argument("--audio-source", required=True)
    parser.add_argument("--rtmp-url", default="")
    parser.add_argument("--rtmp-sink", choices=("auto", "rtmpsink", "rtmp2sink"), default="auto")
    parser.add_argument("--output-file", default="")
    parser.add_argument("--video-bitrate", type=int, default=2500)
    parser.add_argument("--video-encoder", choices=("x264", "nvenc", "auto"), default="nvenc")
    parser.add_argument("--metrics-file", default="")
    parser.add_argument("--diagnostic-interval-seconds", type=float, default=5.0)
    parser.add_argument("--rtmp-restart-max", type=int, default=0)
    parser.add_argument("--rtmp-restart-delay-seconds", type=float, default=2.0)
    parser.add_argument("--rtmp-no-ack-timeout", type=float, default=35.0)
    parser.add_argument("--rtmp-no-ack-min-bytes", type=int, default=5_000_000)
    parser.add_argument("--rtmp-stale-ack-timeout", type=float, default=45.0)
    parser.add_argument("--rtmp-stale-ack-min-bytes", type=int, default=30_000_000)
    parser.add_argument("--rtmp-ack-warning-interval", type=float, default=30.0)
    parser.add_argument("--rtmp-fail-on-ack-lag", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--disable-audio-dynamics", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
