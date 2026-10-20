from __future__ import annotations

from typing import Any


def choose_encoder(
    requested: object,
    *,
    nvenc_available: bool,
    x264_available: bool,
) -> dict[str, Any]:
    requested_name = str(
        requested or "auto"
    ).strip().lower()

    if requested_name not in {
        "auto",
        "nvenc",
        "x264",
    }:
        requested_name = "auto"

    if requested_name in {
        "auto",
        "nvenc",
    }:
        if nvenc_available:
            return {
                "requested": requested_name,
                "selected": "nvenc",
                "element": "nvh264enc",
                "fallback": False,
                "reason": "",
            }

        if x264_available:
            return {
                "requested": requested_name,
                "selected": "x264",
                "element": "x264enc",
                "fallback": True,
                "reason": "nvenc_unavailable",
            }

    if requested_name == "x264":
        if x264_available:
            return {
                "requested": requested_name,
                "selected": "x264",
                "element": "x264enc",
                "fallback": False,
                "reason": "",
            }

        if nvenc_available:
            return {
                "requested": requested_name,
                "selected": "nvenc",
                "element": "nvh264enc",
                "fallback": True,
                "reason": "x264_unavailable",
            }

    return {
        "requested": requested_name,
        "selected": "",
        "element": "",
        "fallback": False,
        "reason": "no_encoder_available",
    }


def choose_sink(
    requested: object,
    *,
    scheme: object,
    rtmp2_available: bool,
    rtmps_available: bool,
) -> dict[str, Any]:
    requested_name = str(
        requested or "auto"
    ).strip().lower()

    if requested_name not in {
        "auto",
        "rtmp2sink",
        "rtmpsink",
    }:
        requested_name = "auto"

    scheme_name = str(
        scheme or ""
    ).strip().lower()

    preferred = requested_name

    if preferred == "auto":
        preferred = (
            "rtmpsink"
            if scheme_name == "rtmps"
            else "rtmp2sink"
        )

    alternate = (
        "rtmp2sink"
        if preferred == "rtmpsink"
        else "rtmpsink"
    )

    available = {
        "rtmp2sink": bool(
            rtmp2_available
        ),
        "rtmpsink": bool(
            rtmps_available
        ),
    }

    if available[preferred]:
        return {
            "requested": requested_name,
            "selected": preferred,
            "element": preferred,
            "fallback": False,
            "reason": "",
        }

    if available[alternate]:
        return {
            "requested": requested_name,
            "selected": alternate,
            "element": alternate,
            "fallback": True,
            "reason":
                f"{preferred}_unavailable",
        }

    return {
        "requested": requested_name,
        "selected": "",
        "element": "",
        "fallback": False,
        "reason": "no_sink_available",
    }


def select_components(
    *,
    requested_encoder: object,
    requested_sink: object,
    destination_scheme: object,
    capabilities: object,
) -> dict[str, Any]:
    caps = (
        capabilities
        if isinstance(
            capabilities,
            dict,
        )
        else {}
    )

    encoder = choose_encoder(
        requested_encoder,
        nvenc_available=bool(
            caps.get("nvh264enc")
        ),
        x264_available=bool(
            caps.get("x264enc")
        ),
    )

    sink = choose_sink(
        requested_sink,
        scheme=destination_scheme,
        rtmp2_available=bool(
            caps.get("rtmp2sink")
        ),
        rtmps_available=bool(
            caps.get("rtmpsink")
        ),
    )

    return {
        "encoder": encoder,
        "sink": sink,
        "ready": bool(
            encoder["selected"]
            and sink["selected"]
        ),
    }
