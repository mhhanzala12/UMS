"""Validation and defaults for downloader options shared by the Qt bridge and tests."""
from __future__ import annotations

from typing import Any


OUTPUT_CONTAINERS = frozenset({
    "original", "mp4", "mkv", "webm", "mov", "avi", "3gp", "ts",
    "mpeg", "ogv", "m4v", "mp3", "m4a", "aac", "opus", "ogg",
    "flac", "wav", "aiff", "wma",
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


def sanitize_download_options(value: Any) -> dict[str, Any]:
    """Return a bounded, JSON-safe options object; reject invalid output targets."""
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

    # Preset controls are deliberately closed sets. Free-form profile, level,
    # bitrate, FPS, and dimensions remain validated by the FFmpeg argument builder.
    allowed = {
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
    for key, values in allowed.items():
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

    return result
