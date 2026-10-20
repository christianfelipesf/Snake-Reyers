from __future__ import annotations

from dataclasses import (
    asdict,
    dataclass,
)
from typing import Any

from cobrinha_server.core.settings import (
    OUTPUT_AUDIO_CHANNELS,
    OUTPUT_AUDIO_RATE,
    OUTPUT_FPS,
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
)
from cobrinha_server.services.output_redaction import (
    public_destination,
)
from cobrinha_server.services.output_selector import (
    select_components,
)


_ALLOWED_ENCODERS = {
    "auto",
    "nvenc",
    "x264",
}

_ALLOWED_SINKS = {
    "auto",
    "rtmp2sink",
    "rtmpsink",
}


@dataclass(frozen=True)
class OutputConfig:
    width: int = OUTPUT_WIDTH
    height: int = OUTPUT_HEIGHT
    fps: int = OUTPUT_FPS
    audio_rate: int = (
        OUTPUT_AUDIO_RATE
    )
    audio_channels: int = (
        OUTPUT_AUDIO_CHANNELS
    )
    video_encoder: str = "nvenc"
    destination_sink: str = "rtmp2sink"
    video_bitrate_kbps: int = 2500
    audio_bitrate_kbps: int = 160
    keyframe_seconds: int = 2
    sink_sync: bool = True
    use_audiorate: bool = True


def normalize_config(
    raw: object = None,
) -> OutputConfig:
    data = (
        raw
        if isinstance(raw, dict)
        else {}
    )

    encoder = str(
        data.get(
            "video_encoder",
            "nvenc",
        )
        or "nvenc"
    ).strip().lower()

    if encoder not in _ALLOWED_ENCODERS:
        encoder = "nvenc"

    sink = str(
        data.get(
            "destination_sink",
            "rtmp2sink",
        )
        or "rtmp2sink"
    ).strip().lower()

    if sink not in _ALLOWED_SINKS:
        sink = "rtmp2sink"

    return OutputConfig(
        width=OUTPUT_WIDTH,
        height=OUTPUT_HEIGHT,
        fps=max(
            15,
            min(
                60,
                int(
                    data.get(
                        "fps",
                        OUTPUT_FPS,
                    )
                    or OUTPUT_FPS
                ),
            ),
        ),
        audio_rate=OUTPUT_AUDIO_RATE,
        audio_channels=
            OUTPUT_AUDIO_CHANNELS,
        video_encoder=encoder,
        destination_sink=sink,
        video_bitrate_kbps=max(
            1500,
            min(
                12000,
                int(
                    data.get(
                        "video_bitrate_kbps",
                        2500,
                    )
                    or 2500
                ),
            ),
        ),
        audio_bitrate_kbps=max(
            96,
            min(
                320,
                int(
                    data.get(
                        "audio_bitrate_kbps",
                        160,
                    )
                    or 160
                ),
            ),
        ),
        keyframe_seconds=max(
            1,
            min(
                5,
                int(
                    data.get(
                        "keyframe_seconds",
                        2,
                    )
                    or 2
                ),
            ),
        ),
        sink_sync=True,
        use_audiorate=True,
    )


def build_plan(
    raw_config: object = None,
    *,
    destination_url: str = "",
    capabilities: object = None,
) -> dict[str, Any]:
    config = normalize_config(
        raw_config
    )

    destination = public_destination(
        destination_url
    )

    selection = select_components(
        requested_encoder=
            config.video_encoder,
        requested_sink=
            config.destination_sink,
        destination_scheme=
            destination.get(
                "scheme"
            ),
        capabilities=(
            capabilities
            if capabilities is not None
            else {
                "nvh264enc": True,
                "x264enc": True,
                "rtmp2sink": True,
                "rtmpsink": True,
            }
        ),
    )

    encoder_element = str(
        selection["encoder"][
            "element"
        ]
    )

    sink_element = str(
        selection["sink"][
            "element"
        ]
    )

    return {
        "version": 1,
        "executes": False,
        "resolution": {
            "width": config.width,
            "height": config.height,
        },
        "fps": config.fps,
        "config":
            asdict(config),
        "destination":
            destination,
        "selection":
            selection,
        "video_chain": [
            "video_source",
            "videoconvert",
            "videoscale",
            (
                "video/x-raw,"
                f"width={config.width},"
                f"height={config.height},"
                f"framerate={config.fps}/1"
            ),
            encoder_element,
            "h264parse",
            "queue",
        ],
        "audio_chain": [
            "audio_source",
            "audioconvert",
            "audioresample",
            "audiorate",
            (
                "audio/x-raw,"
                f"rate={config.audio_rate},"
                f"channels={config.audio_channels}"
            ),
            "voaacenc",
            "queue",
        ],
        "container_chain": [
            "flvmux",
            "streamable=true",
            "queue",
            sink_element,
            "sync=true",
        ],
        "invariants": {
            "resolution_locked":
                True,
            "audiorate":
                True,
            "sink_sync":
                True,
            "flvmux_streamable":
                True,
            "audio_queue_leaky":
                False,
            "post_mux_queue_leaky":
                False,
        },
    }
