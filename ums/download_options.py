"""Validation and defaults for downloader options shared by the QML bridge and engine.

Validate expensive-to-discover FFmpeg mistakes before a URL is downloaded. Keep
this module independent of Qt and FFmpeg so it can be used by tests and tooling.
"""
from __future__ import annotations

import math
import re
from typing import Any


OUTPUT_CONTAINERS = frozenset({
    "original", "mp4", "mkv", "webm", "mov", "avi", "3gp", "ts",
    "mpeg", "ogv", "m4v", "mp3", "m4a", "aac", "opus", "ogg",
    "flac", "wav", "aiff", "wma",
})
AUDIO_ONLY_CONTAINERS = frozenset({
    "mp3", "m4a", "aac", "opus", "ogg", "flac", "wav", "aiff", "wma",
})

DEFAULT_DOWNLOAD_OPTIONS: dict[str, Any] = {
    "format": "bestvideo+bestaudio/best",
    "container": "original",
    "video_codec": "copy",
    "audio_codec": "copy",
    "video_encoder": "Auto",
    "profile": "",
    "level": "",
    "pixel_format": "Auto",
    "color_space": "Auto",
    "color_range": "Auto",
    "rate_control": "Source",
    "video_bitrate": "",
    "audio_bitrate": "",
    "crf": "23",
    "encoder_preset": "medium",
    "fps": "Source",
    "fps_mode": "CFR",
    "resolution": "Source",
    "custom_scale": "",
    "sample_rate": "Source",
    "channels": "Source",
    "write_subtitles": False,
    "write_automatic_subtitles": False,
    "embed_subtitles": False,
    "preserve_metadata": True,
    "download_thumbnail": False,
}

_STRING_LIMITS = {
    "format": 512,
    "video_codec": 24,
    "audio_codec": 24,
    "video_encoder": 32,
    "profile": 32,
    "level": 16,
    "pixel_format": 24,
    "color_space": 24,
    "color_range": 12,
    "rate_control": 12,
    "video_bitrate": 24,
    "audio_bitrate": 24,
    "crf": 3,
    "encoder_preset": 16,
    "fps": 16,
    "fps_mode": 8,
    "resolution": 16,
    "custom_scale": 16,
    "sample_rate": 8,
    "channels": 8,
}
_BOOLEAN_KEYS = (
    "write_subtitles",
    "write_automatic_subtitles",
    "embed_subtitles",
    "preserve_metadata",
    "download_thumbnail",
)
_ALLOWED = {
    "video_codec": {"copy", "h264", "hevc", "av1", "vp9", "vp8", "mpeg4", "mpeg2", "theora"},
    "audio_codec": {"copy", "aac", "mp3", "opus", "vorbis", "flac", "pcm", "alac"},
    "video_encoder": {
        "Auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf", "libx265",
        "hevc_nvenc", "hevc_qsv", "hevc_amf", "libsvtav1", "libaom-av1",
        "av1_nvenc", "libvpx-vp9", "libvpx", "mpeg4", "mpeg2video", "libtheora",
    },
    "pixel_format": {"Auto", "yuv420p", "yuv422p", "yuv444p", "yuv420p10le", "yuv422p10le", "yuv444p10le", "p010le", "rgb24"},
    "color_space": {"Auto", "bt709", "bt2020nc", "smpte170m", "bt470bg", "smpte240m"},
    "color_range": {"Auto", "tv", "pc"},
    "rate_control": {"Source", "CRF", "CBR", "VBR", "CQ"},
    "encoder_preset": {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"},
    "fps_mode": {"CFR", "VFR"},
    "resolution": {"Source", "2160p", "1440p", "1080p", "720p", "540p", "480p", "360p", "240p", "Custom"},
    "sample_rate": {"Source", "22050", "32000", "44100", "48000", "96000", "192000"},
    "channels": {"Source", "Mono", "Stereo"},
}
_ENCODERS_BY_CODEC = {
    "h264": {"libx264", "h264_nvenc", "h264_qsv", "h264_amf"},
    "hevc": {"libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf"},
    "av1": {"libsvtav1", "libaom-av1", "av1_nvenc"},
    "vp9": {"libvpx-vp9"},
    "vp8": {"libvpx"},
    "mpeg4": {"mpeg4"},
    "mpeg2": {"mpeg2video"},
    "theora": {"libtheora"},
}
_BITRATE_RE = re.compile(r"^(?:\\d+(?:\\.\\d+)?)(?:[kKmMgG])?$")
_PROFILE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_LEVEL_RE = re.compile(r"^\\d{1,2}(?:\\.\\d{1,2})?$")
_DIMENSIONS_RE = re.compile(r"^(\\d{2,5})x(\\d{2,5})$", re.IGNORECASE)


def _parse_bitrate(value: str, label: str) -> str:
    text = str(value or "").strip().replace(" ", "")
    if not text:
        return ""
    if not _BITRATE_RE.fullmatch(text):
        raise ValueError(f"{label} must look like 4500k, 2M, or 192k.")
    amount = re.match(r"^\\d+(?:\\.\\d+)?", text)
    if not amount or float(amount.group(0)) <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return text


def sanitize_download_options(value: Any) -> dict[str, Any]:
    """Return bounded, JSON-safe options and reject invalid combinations early."""
    if not isinstance(value, dict):
        raise ValueError("Download options must be a JSON object.")

    result = dict(DEFAULT_DOWNLOAD_OPTIONS)
    raw_container = value.get("container", result["container"])
    if not isinstance(raw_container, str):
        raise ValueError("Output container must be a text value.")
    container = raw_container.strip().lower()
    if container not in OUTPUT_CONTAINERS:
        raise ValueError(f"Unsupported output container: {container or '(empty)'}")
    result["container"] = container

    for key, limit in _STRING_LIMITS.items():
        raw = value.get(key, result[key])
        if raw is None:
            raw = ""
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            raise ValueError(f"Invalid value for {key}.")
        text = str(raw).strip()
        if len(text) > limit:
            raise ValueError(f"{key} is too long (maximum {limit} characters).")
        result[key] = text

    if not result["format"]:
        raise ValueError("Choose a source quality/format expression.")

    for key, values in _ALLOWED.items():
        if result[key] not in values:
            raise ValueError(f"Unsupported {key.replace('_', ' ')}: {result[key] or '(empty)'}")

    try:
        quality = int(result["crf"])
    except ValueError as exc:
        raise ValueError("CRF / quality must be an integer between 0 and 63.") from exc
    if not 0 <= quality <= 63:
        raise ValueError("CRF / quality must be an integer between 0 and 63.")

    for key in _BOOLEAN_KEYS:
        raw = value.get(key, result[key])
        if isinstance(raw, bool):
            result[key] = raw
        elif isinstance(raw, (str, int)):
            result[key] = str(raw).strip().lower() in {"1", "true", "yes", "on"}
        else:
            raise ValueError(f"Invalid checkbox value for {key}.")

    result["video_bitrate"] = _parse_bitrate(result["video_bitrate"], "Video bitrate")
    result["audio_bitrate"] = _parse_bitrate(result["audio_bitrate"], "Audio bitrate")

    # Older legacy profiles used FPS="VFR". Migrate that spelling to the
    # separate frame-mode control rather than treating it as a frame rate.
    if result["fps"].casefold() in {"vfr", "variable"}:
        result["fps"] = "Source"
        result["fps_mode"] = "VFR"
    elif result["fps"].casefold() != "source":
        try:
            fps_value = float(result["fps"])
        except ValueError as exc:
            raise ValueError("FPS must be Source or a number between 1 and 240.") from exc
        if not math.isfinite(fps_value) or not 1 <= fps_value <= 240:
            raise ValueError("FPS must be Source or a number between 1 and 240.")

    # A stale custom size used to override a newly selected 720p/1080p preset
    # because the FFmpeg builder preferred custom_scale whenever it was nonempty.
    if result["resolution"] == "Custom":
        match = _DIMENSIONS_RE.fullmatch(result["custom_scale"])
        if not match:
            raise ValueError("Custom resolution must look like 320x240.")
        width, height = (int(match.group(1)), int(match.group(2)))
        if not (16 <= width <= 16384 and 16 <= height <= 16384):
            raise ValueError("Custom dimensions must be between 16 and 16384 pixels.")
        result["custom_scale"] = f"{width}x{height}"
    else:
        result["custom_scale"] = ""

    if result["profile"] and not _PROFILE_RE.fullmatch(result["profile"]):
        raise ValueError("Profile must be a short codec profile name, e.g. high or main.")
    if result["level"] and not _LEVEL_RE.fullmatch(result["level"]):
        raise ValueError("Codec level must be numeric, for example 4.1.")

    audio_only = container in AUDIO_ONLY_CONTAINERS
    video_codec = result["video_codec"]
    if not audio_only:
        if video_codec == "copy":
            if result["video_encoder"] != "Auto":
                raise ValueError("Choose a video codec before selecting an explicit video encoder.")
            if (
                result["fps"].casefold() != "source"
                or result["resolution"] != "Source"
                or result["profile"]
                or result["level"]
                or result["pixel_format"] != "Auto"
                or result["color_space"] != "Auto"
                or result["color_range"] != "Auto"
            ):
                raise ValueError(
                    "FPS, scaling, profile, pixel-format, and color controls require video re-encoding. "
                    "Choose a video codec other than copy."
                )
            if result["rate_control"] != "Source" or result["video_bitrate"]:
                raise ValueError("Video rate control and bitrate require a re-encoded video codec.")
        else:
            explicit_encoder = result["video_encoder"]
            if explicit_encoder != "Auto" and explicit_encoder not in _ENCODERS_BY_CODEC[video_codec]:
                raise ValueError(
                    f"Encoder {explicit_encoder} is not compatible with the {video_codec} video codec."
                )
            if result["rate_control"] in {"CBR", "VBR"} and not result["video_bitrate"]:
                raise ValueError(f"{result['rate_control']} mode requires a video bitrate, e.g. 2500k.")

    return result
