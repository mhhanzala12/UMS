"""yt-dlp + FFmpeg media engine. All processing happens locally."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from .config import APP_DIR

_LOG = logging.getLogger(__name__)

MEDIA_EXTENSIONS = {
    ".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".3gp", ".ts",
    ".mpg", ".mpeg", ".ogv", ".mp3", ".m4a", ".aac", ".ogg", ".opus",
    ".flac", ".wav", ".aiff", ".wma", ".alac",
}
VIDEO_CONTAINERS = {"mp4", "mkv", "webm", "mov", "avi", "3gp", "ts", "mpeg", "ogv", "m4v"}
AUDIO_CONTAINERS = {"mp3", "m4a", "aac", "ogg", "opus", "flac", "wav", "aiff", "alac", "wma"}


class MediaError(RuntimeError):
    pass


class CancelledError(MediaError):
    pass


SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".ttml"}
THUMBNAIL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_COOKIE_BROWSERS = {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale"}

# Encoder tables used to be rebuilt on every _ffmpeg_args() call; they are constants.
_H264_ENCODERS = ("libx264", "h264_nvenc", "h264_qsv", "h264_amf")
_HEVC_ENCODERS = ("libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf")
ENCODER_PREFERENCES = {
    "h264": _H264_ENCODERS, "h.264": _H264_ENCODERS,
    "hevc": _HEVC_ENCODERS, "h265": _HEVC_ENCODERS,
    "av1": ("libsvtav1", "libaom-av1", "av1_nvenc"),
    "vp9": ("libvpx-vp9",), "vp8": ("libvpx",),
    "mpeg4": ("mpeg4",), "mpeg2": ("mpeg2video",), "theora": ("libtheora",),
}
ENCODER_FAMILIES = {codec: frozenset(names) for codec, names in ENCODER_PREFERENCES.items()}
DEFAULT_VIDEO_ENCODERS = {
    "h264": "libx264", "h.264": "libx264", "hevc": "libx265", "h265": "libx265",
    "av1": "libsvtav1", "vp9": "libvpx-vp9", "vp8": "libvpx",
    "mpeg4": "mpeg4", "mpeg2": "mpeg2video", "theora": "libtheora",
}
_ENCODER_LINE = re.compile(r"^\s*[VASD.]{6}\s+(\S+)")

# Hide the console window FFmpeg/ffprobe would otherwise flash in a windowed Windows build.
_NO_WINDOW: dict = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}


def _which(name: str, configured: Optional[str] = None) -> Optional[str]:
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return str(p)
    return shutil.which(name)


def is_http_url(value: str) -> bool:
    """Return whether value is a syntactically valid absolute HTTP(S) URL."""
    raw = str(value or "").strip()
    if not raw or any(char.isspace() for char in raw):
        return False
    try:
        parsed = urlsplit(raw)
        # Accessing .port also validates malformed and out-of-range port values.
        _ = parsed.port
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


def network_options(settings: Optional[dict], default_browser: str = "None") -> dict:
    """yt-dlp proxy + browser-cookie options derived from the user's settings.

    This logic used to be copy-pasted in three places (analysis, download, music).
    """
    settings = settings or {}
    opts: dict = {}
    mode = str(settings.get("connection_mode") or "Automatic").lower()
    if mode == "direct":
        opts["proxy"] = ""
    elif mode == "proxy":
        proxy = str(settings.get("proxy_url") or "").strip()
        if not proxy:
            raise MediaError("Proxy mode is selected, but no proxy URL is configured.")
        opts["proxy"] = proxy
    browser = str(settings.get("cookies_browser") or default_browser).strip().lower()
    if browser in SUPPORTED_COOKIE_BROWSERS:
        profile = str(settings.get("cookies_profile") or "").strip()
        opts["cookiesfrombrowser"] = (browser, profile or None)
    return opts


# `ffmpeg -version` / `ffmpeg -encoders` cost up to ~17 s of blocking subprocess time.
# Results never change for a given binary, so they are probed once per (path, mtime).
_FFMPEG_INFO_CACHE: dict[tuple[str, int], dict] = {}
_FFMPEG_INFO_LOCK = threading.Lock()


def _run_quiet(args: list[str], timeout: float) -> str:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace", **_NO_WINDOW)
    return (p.stdout or "") + "\n" + (p.stderr or "")


def ffmpeg_info(ffmpeg: str, refresh: bool = False) -> dict:
    """Cached FFmpeg version string and encoder list (probed concurrently)."""
    try:
        key = (ffmpeg, os.stat(ffmpeg).st_mtime_ns)
    except OSError:
        key = (ffmpeg, 0)
    if not refresh:
        with _FFMPEG_INFO_LOCK:
            cached = _FFMPEG_INFO_CACHE.get(key)
        if cached is not None:
            return cached

    def probe_version():
        try:
            return _run_quiet([ffmpeg, "-version"], 5).strip().splitlines()[0][:120]
        except (OSError, subprocess.SubprocessError) as exc:
            _LOG.warning("FFmpeg version probe failed for %s: %s", ffmpeg, exc)
            return "Found (version check failed)"

    def probe_encoders():
        try:
            found = []
            for line in _run_quiet([ffmpeg, "-hide_banner", "-encoders"], 12).splitlines():
                match = _ENCODER_LINE.match(line)
                if match and match.group(1) != "=":
                    found.append(match.group(1))
            return sorted(set(found))
        except (OSError, subprocess.SubprocessError) as exc:
            _LOG.warning("FFmpeg encoder probe failed for %s: %s", ffmpeg, exc)
            return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        version_future = pool.submit(probe_version)
        encoders_future = pool.submit(probe_encoders)
        info = {"version": version_future.result(), "encoders": encoders_future.result()}
    if info["encoders"]:  # never cache a failed probe
        with _FFMPEG_INFO_LOCK:
            _FFMPEG_INFO_CACHE[key] = info
    return info


def list_encoders(ffmpeg: str) -> list[str]:
    return list(ffmpeg_info(ffmpeg)["encoders"])


def _ytdlp_version() -> Optional[str]:
    """yt-dlp's version without importing it (the import alone costs ~0.2 s of CPU)."""
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version("yt-dlp")
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    try:  # frozen builds without dist-info metadata
        import yt_dlp
        return getattr(yt_dlp, "__version__", "installed")
    except ImportError:
        return None


def tool_status(ffmpeg_path: Optional[str] = None, ffprobe_path: Optional[str] = None,
                refresh: bool = False) -> dict:
    ytdlp_version = _ytdlp_version()
    ffmpeg = _which("ffmpeg", ffmpeg_path)
    ffprobe = _which("ffprobe", ffprobe_path)
    info = ffmpeg_info(ffmpeg, refresh) if ffmpeg else {"version": None, "encoders": []}
    return {
        "yt_dlp": ytdlp_version,
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "ffmpeg_version": info["version"],
        "encoders": list(info["encoders"]),
    }


def _thumbnail_candidates(info: dict) -> list[str]:
    """Return unique thumbnail URLs, preferring larger advertised images."""
    rows = []
    for item in info.get("thumbnails") or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        try:
            width = max(0, int(item.get("width") or 0))
            height = max(0, int(item.get("height") or 0))
            preference = int(item.get("preference") or 0)
        except (TypeError, ValueError, OverflowError):
            width = height = preference = 0
        rows.append((width * height, preference, str(item["url"])))
    # Pixel area is the strongest useful signal; provider preference breaks ties.
    rows.sort(key=lambda row: (row[0], row[1]), reverse=True)

    ordered = [row[2] for row in rows]
    primary = str(info.get("thumbnail") or "").strip()
    if primary and primary not in ordered:
        ordered.append(primary)
    unique = []
    seen = set()
    for url in ordered:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    return unique[:8]


def _download_thumbnail_data(url: str, timeout: float = 3.5,
                             max_bytes: int = 4 * 1024 * 1024) -> bytes:
    """Fetch a bounded raster thumbnail preview on the analysis worker thread."""
    url = str(url or "").strip()
    if not is_http_url(url):
        return b""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 UniversalMediaStudio/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
            if content_type and not content_type.startswith("image/"):
                return b""
            data = response.read(max_bytes + 1)
            if not data or len(data) > max_bytes:
                _LOG.debug("Skipped empty or oversized media thumbnail (%s bytes)", len(data))
                return b""
            signature_ok = (
                data.startswith(bytes((255, 216, 255)))  # JPEG
                or data.startswith(bytes((137, 80, 78, 71, 13, 10, 26, 10)))  # PNG
                or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")
                or data.startswith((b"GIF87a", b"GIF89a"))
            )
            return data if signature_ok else b""
    except Exception as exc:
        _LOG.debug("Thumbnail preview download failed for %s: %s", url, exc)
        return b""


def _download_thumbnail_candidates(urls: list[str], max_candidates: int = 4) -> bytes:
    """Try several thumbnail variants so one stale CDN URL does not hide the preview."""
    for url in (urls or [])[:max_candidates]:
        data = _download_thumbnail_data(url)
        if data:
            return data
    return b""


def analyze_url(url: str, cancel_event: Optional[threading.Event] = None, settings: Optional[dict] = None) -> dict:
    """Fetch source metadata, the best preview image URL, and stream details."""
    url = str(url or "").strip()
    if not is_http_url(url):
        raise MediaError("Enter a valid absolute http:// or https:// media URL with a hostname.")
    try:
        import yt_dlp
    except ImportError as exc:
        raise MediaError("yt-dlp is missing. Run the installer script or: pip install -r requirements.txt") from exc
    if cancel_event and cancel_event.is_set():
        raise CancelledError("Analysis cancelled.")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "ignoreerrors": False,
        "socket_timeout": 20,
        "extractor_retries": 2,
    }
    opts.update(network_options(settings))
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise MediaError(f"Could not inspect this URL: {exc}") from exc
    if not info:
        raise MediaError("The source did not return media information.")
    formats = []
    for f in info.get("formats") or []:
        if not f.get("url"):
            continue
        width = f.get("width")
        height = f.get("height")
        fps = f.get("fps")
        size = f.get("filesize") or f.get("filesize_approx")
        formats.append({
            "format_id": str(f.get("format_id", "?")),
            "ext": str(f.get("ext", "?")),
            "resolution": f.get("resolution") or (
                f"{width}x{height}" if width and height else
                (f"{height}p" if height else "audio only")
            ),
            "width": width,
            "height": height,
            "fps": fps,
            "vcodec": f.get("vcodec"),
            "acodec": f.get("acodec"),
            "filesize": size,
            "tbr": f.get("tbr"),
            "abr": f.get("abr"),
            "note": str(f.get("format_note") or ""),
            "format": str(f.get("format") or ""),
        })

    def has_codec(value):
        return bool(value) and str(value).lower() != "none"

    def format_rank(row, video=False):
        try:
            height_value = float(row.get("height") or 0)
            fps_value = float(row.get("fps") or 0)
            bitrate_value = float(row.get("tbr") or row.get("abr") or 0)
            size_value = float(row.get("filesize") or 0)
        except (TypeError, ValueError, OverflowError):
            height_value = fps_value = bitrate_value = size_value = 0
        return (
            height_value if video else 0,
            fps_value if video else 0,
            bitrate_value,
            size_value,
            str(row.get("format_id") or ""),
        )

    # Many extractors expose separate video and audio streams and leave the
    # selected-format summary fields blank until a format is chosen. Derive a
    # useful preview summary from the best available source streams.
    formats.sort(key=lambda row: format_rank(row, has_codec(row.get("vcodec"))), reverse=True)
    video_formats = [row for row in formats if has_codec(row.get("vcodec"))]
    audio_formats = [row for row in formats if has_codec(row.get("acodec"))]
    combined_formats = [
        row for row in formats
        if has_codec(row.get("vcodec")) and has_codec(row.get("acodec"))
    ]
    best_video = max(video_formats, key=lambda row: format_rank(row, True), default={})
    best_audio = max(audio_formats, key=lambda row: format_rank(row), default={})
    best_combined = max(combined_formats, key=lambda row: format_rank(row, True), default={})

    thumbnails = _thumbnail_candidates(info)
    thumbnail_data = _download_thumbnail_candidates(thumbnails)
    upload_date = info.get("upload_date") or info.get("release_date") or ""
    width = info.get("width") or best_video.get("width")
    height = info.get("height") or best_video.get("height")
    resolution = info.get("resolution") or (
        f"{width}x{height}" if width and height else best_video.get("resolution") or ""
    )
    top_vcodec = info.get("vcodec")
    top_acodec = info.get("acodec")
    if not has_codec(top_vcodec):
        top_vcodec = best_video.get("vcodec") or ""
    if not has_codec(top_acodec):
        top_acodec = best_combined.get("acodec") or best_audio.get("acodec") or ""
    summary_format = best_combined or best_video or best_audio
    return {
        "id": str(info.get("id") or ""),
        "extractor": str(info.get("extractor_key") or info.get("extractor") or ""),
        "title": str(info.get("title") or info.get("fulltitle") or info.get("track") or "Untitled media"),
        "description": str(info.get("description") or "")[:12000],
        "duration": info.get("duration"),
        "thumbnail": thumbnails[0] if thumbnails else "",
        "thumbnail_data": thumbnail_data,
        "thumbnails": thumbnails,
        "uploader": str(info.get("uploader") or info.get("channel") or info.get("creator") or info.get("artist") or ""),
        "channel": str(info.get("channel") or info.get("uploader") or ""),
        "channel_url": str(info.get("channel_url") or info.get("uploader_url") or ""),
        "creator": str(info.get("creator") or info.get("artist") or ""),
        "upload_date": str(upload_date),
        "release_date": str(info.get("release_date") or ""),
        "timestamp": info.get("timestamp"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "channel_follower_count": info.get("channel_follower_count"),
        "age_limit": info.get("age_limit"),
        "availability": str(info.get("availability") or ""),
        "categories": [str(value) for value in (info.get("categories") or [])][:20],
        "tags": [str(value) for value in (info.get("tags") or [])][:40],
        "webpage_url": str(info.get("webpage_url") or url),
        "format": str(info.get("format") or summary_format.get("format") or ""),
        "format_id": str(info.get("format_id") or summary_format.get("format_id") or ""),
        "ext": str(info.get("ext") or summary_format.get("ext") or ""),
        "resolution": str(resolution or ""),
        "width": width,
        "height": height,
        "fps": info.get("fps") or best_video.get("fps"),
        # Do not report an individual video-only stream as the total file size.
        # When yt-dlp has not selected a progressive format, the per-stream
        # sizes remain visible in the Available Formats table.
        "filesize": info.get("filesize") or info.get("filesize_approx") or best_combined.get("filesize"),
        "vcodec": str(top_vcodec or ""),
        "acodec": str(top_acodec or ""),
        "best_video_format": dict(best_video),
        "best_audio_format": dict(best_audio),
        "formats": formats,
        "subtitles": sorted((info.get("subtitles") or {}).keys()),
        "automatic_captions": sorted((info.get("automatic_captions") or {}).keys()),
        "is_live": bool(info.get("is_live")),
        "live_status": str(info.get("live_status") or ""),
    }


def _safe_stem(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    return (value or "media")[:170]


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for n in range(1, 10000):
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise MediaError(f"Could not find a free filename for {path.name}")


def _check_cancel(cancel_event: Optional[threading.Event]):
    if cancel_event and cancel_event.is_set():
        raise CancelledError("Cancelled by user.")


def _parse_bitrate(value: str) -> Optional[str]:
    value = (value or "").strip()
    if not value:
        return None
    if not re.fullmatch(r"\d+(?:\.\d+)?\s*(?:k|K|M|G)?", value):
        raise MediaError("Bitrate must look like 2500k, 2M, or 192k.")
    return re.sub(r"\s+", "", value)


def _ffmpeg_args(source: Path, target: Path, options: dict, subtitle_files=None) -> list[str]:
    """Build a validated FFmpeg command for the selected output profile."""
    container = (options.get("container") or "original").lower()
    is_audio = container in AUDIO_CONTAINERS or bool(options.get("audio_only"))
    vcodec_choice = (options.get("video_codec") or "copy").lower()
    acodec_choice = (options.get("audio_codec") or "copy").lower()
    # Sensible defaults for audio-only containers: a copied source codec cannot
    # simply be renamed to an MP3/FLAC/WAV filename.
    if acodec_choice == "copy" and container in AUDIO_CONTAINERS:
        acodec_choice = {
            "mp3": "mp3", "m4a": "aac", "aac": "aac", "opus": "opus",
            "ogg": "vorbis", "flac": "flac", "wav": "pcm", "aiff": "pcm",
            "alac": "alac", "wma": "wma",
        }.get(container, "copy")
    available = set(options.get("_available_encoders") or [])
    def preferred_encoder(codec, default):
        if not available:
            return default
        return next((item for item in ENCODER_PREFERENCES.get(codec, (default,)) if item in available), default)
    vmap = {codec: preferred_encoder(codec, default) for codec, default in DEFAULT_VIDEO_ENCODERS.items()}
    vmap["copy"] = "copy"
    encoder_override = str(options.get("video_encoder") or "Auto")
    if encoder_override != "Auto":
        if vcodec_choice == "copy" or encoder_override not in ENCODER_FAMILIES.get(vcodec_choice, frozenset()):
            raise MediaError(f"Encoder {encoder_override} is not compatible with video codec {vcodec_choice}.")
        if available and encoder_override not in available:
            raise MediaError(f"Encoder {encoder_override} is not present in the installed FFmpeg build.")
        vmap[vcodec_choice] = encoder_override
    amap = {
        "aac": "aac", "mp3": "libmp3lame", "opus": "libopus", "vorbis": "libvorbis",
        "flac": "flac", "pcm": "pcm_s16le", "alac": "alac", "wma": "wmav2", "copy": "copy",
    }
    if container == "aiff" and acodec_choice == "pcm":
        amap["pcm"] = "pcm_s16be"
    if vcodec_choice not in vmap:
        raise MediaError(f"Unknown video codec: {vcodec_choice}")
    if acodec_choice not in amap:
        raise MediaError(f"Unknown audio codec: {acodec_choice}")

    if container == "webm":
        # This guard protects direct engine callers too. _finalize normally
        # supplies the copy-safe markers after ffprobe has inspected the source.
        if not is_audio and vcodec_choice == "copy" and not options.get("_webm_video_copy_safe"):
            raise MediaError(
                "WebM cannot copy an unverified video stream. Re-run analysis or install ffprobe so the source codec can be checked."
            )
        if not is_audio and vcodec_choice != "copy" and vcodec_choice not in {"vp8", "vp9", "av1"}:
            raise MediaError("WebM video must use VP8, VP9, or AV1.")
        if acodec_choice == "copy" and not options.get("_webm_audio_copy_safe"):
            raise MediaError(
                "WebM cannot copy an unverified audio stream. Re-run analysis or install ffprobe so the source codec can be checked."
            )
        if acodec_choice != "copy" and acodec_choice not in {"opus", "vorbis"}:
            raise MediaError("WebM audio must use Opus or Vorbis.")

    cmd = ["-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
    subtitle_files = list(subtitle_files or [])
    if options.get("embed_subtitles") and not is_audio:
        for sub in subtitle_files:
            cmd += ["-i", str(sub)]
    if is_audio:
        # MP3 cover art is exposed as attached-picture video streams. Map only
        # the first audio stream so audio exports never remux album art as video.
        cmd += ["-vn", "-map", "0:a:0?"]
        cmd += ["-c:a", amap.get(acodec_choice, "copy")]
        audio_bitrate = _parse_bitrate(options.get("audio_bitrate", ""))
        if audio_bitrate and acodec_choice not in {"copy", "flac", "pcm", "alac"}:
            cmd += ["-b:a", audio_bitrate]
    else:
        cmd += ["-map", "0:v:0?", "-map", "0:a:0?"]
        cmd += ["-c:v", vmap[vcodec_choice]]
        cmd += ["-c:a", amap[acodec_choice]]
        if vcodec_choice != "copy":
            rate_control = (options.get("rate_control") or "CRF").upper()
            # "Source" is meaningful for stream-copy. Once a codec is selected
            # for re-encoding, use the configured quality value rather than
            # silently falling through to FFmpeg's encoder-specific default.
            if rate_control == "SOURCE":
                rate_control = "CRF"
            vbitrate = _parse_bitrate(options.get("video_bitrate", ""))
            encoder = vmap[vcodec_choice]
            crf = str(options.get("crf", "23")).strip()
            if rate_control in {"CRF", "CQ"}:
                if not crf.isdigit() or not (0 <= int(crf) <= 63):
                    raise MediaError("Quality value must be an integer between 0 and 63.")
                if encoder.endswith("_nvenc"):
                    cmd += ["-rc", "vbr", "-cq", crf]
                    if vbitrate:
                        cmd += ["-maxrate", vbitrate]
                elif encoder.endswith("_qsv"):
                    cmd += ["-global_quality", crf]
                elif encoder.endswith("_amf"):
                    cmd += ["-rc", "cqp", "-qp_i", crf, "-qp_p", crf]
                elif encoder == "libtheora":
                    # Theora uses a 0–10 quality scale rather than x264-style CRF.
                    quality = max(0, min(10, round((63 - int(crf)) * 10 / 63)))
                    cmd += ["-q:v", str(quality)]
                elif encoder in {"mpeg4", "mpeg2video"}:
                    # MPEG-4 Part 2 / MPEG-2 use qscale; this is an approximate mapping.
                    quality = max(2, min(31, round(int(crf) * 31 / 63)))
                    cmd += ["-q:v", str(quality)]
                elif encoder in {"libvpx", "libvpx-vp9"}:
                    # libvpx uses a zero bitrate target for constant-quality CRF.
                    cmd += ["-b:v", vbitrate or "0", "-crf", crf]
                else:
                    cmd += ["-crf", crf]
                if rate_control == "CQ" and vbitrate and not encoder.endswith(("_nvenc", "_qsv", "_amf")) and encoder not in {"libvpx", "libvpx-vp9"}:
                    cmd += ["-maxrate", vbitrate]
            elif rate_control in {"CBR", "VBR"}:
                if not vbitrate:
                    raise MediaError(f"{rate_control} mode needs a video bitrate, e.g. 4000k.")
                if encoder.endswith("_nvenc"):
                    cmd += ["-rc", "cbr" if rate_control == "CBR" else "vbr", "-b:v", vbitrate]
                    if rate_control == "CBR":
                        cmd += ["-maxrate", vbitrate, "-bufsize", vbitrate]
                elif encoder.endswith("_amf"):
                    cmd += ["-rc", "cbr" if rate_control == "CBR" else "vbr", "-b:v", vbitrate]
                else:
                    cmd += ["-b:v", vbitrate]
                    if rate_control == "CBR":
                        cmd += ["-minrate", vbitrate, "-maxrate", vbitrate, "-bufsize", vbitrate]
            elif rate_control == "SOURCE":
                pass
            else:
                raise MediaError(f"Unsupported rate-control mode: {rate_control}")

            preset = str(options.get("encoder_preset") or "medium")
            if encoder == "libaom-av1":
                cpu_used = {"ultrafast": "8", "superfast": "7", "veryfast": "6", "faster": "5", "fast": "5", "medium": "4", "slow": "3", "slower": "2", "veryslow": "1", "placebo": "0"}.get(preset, "4")
                cmd += ["-cpu-used", cpu_used]
            elif encoder == "libsvtav1":
                svt_preset = {"ultrafast": "10", "superfast": "9", "veryfast": "8", "faster": "7", "fast": "6", "medium": "6", "slow": "4", "slower": "3", "veryslow": "2", "placebo": "1"}.get(preset, "6")
                cmd += ["-preset", svt_preset]
            elif encoder.endswith("_nvenc"):
                nvenc_preset = {"ultrafast": "p1", "superfast": "p2", "veryfast": "p3", "faster": "p3", "fast": "p4", "medium": "p4", "slow": "p5", "slower": "p6", "veryslow": "p7", "placebo": "p7"}.get(preset, "p4")
                cmd += ["-preset", nvenc_preset]
            elif encoder.endswith("_amf"):
                cmd += ["-quality", "speed" if preset in {"ultrafast", "superfast", "veryfast", "faster", "fast"} else ("quality" if preset in {"slower", "veryslow", "placebo"} else "balanced")]
            elif encoder in {"libvpx", "libvpx-vp9"}:
                cpu_used = {
                    "ultrafast": "8", "superfast": "7", "veryfast": "6",
                    "faster": "5", "fast": "4", "medium": "3",
                    "slow": "2", "slower": "1", "veryslow": "0",
                    "placebo": "0",
                }.get(preset, "3")
                cmd += ["-deadline", "good", "-cpu-used", cpu_used]
            elif encoder in {"libx264", "libx265", "h264_qsv", "hevc_qsv"}:
                cmd += ["-preset", preset]

            profile = str(options.get("profile") or "").strip()
            level = str(options.get("level") or "").strip()
            if profile:
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", profile):
                    raise MediaError("Profile must be a short codec profile name, e.g. high or main.")
                cmd += ["-profile:v", profile]
            if level:
                if not re.fullmatch(r"\d{1,2}(?:\.\d{1,2})?", level):
                    raise MediaError("Level must be numeric, for example 4.1.")
                cmd += ["-level:v", level]
            pixel_format = str(options.get("pixel_format") or "Auto")
            if pixel_format != "Auto":
                if pixel_format not in {"yuv420p", "yuv422p", "yuv444p", "yuv420p10le", "yuv422p10le", "yuv444p10le", "p010le", "rgb24"}:
                    raise MediaError("Unsupported pixel format selection.")
                cmd += ["-pix_fmt", pixel_format]
            color_space = str(options.get("color_space") or "Auto")
            if color_space != "Auto":
                if color_space not in {"bt709", "bt2020nc", "smpte170m", "bt470bg", "smpte240m"}:
                    raise MediaError("Unsupported color space selection.")
                cmd += ["-colorspace", color_space]
            color_range = str(options.get("color_range") or "Auto")
            if color_range != "Auto":
                if color_range not in {"tv", "pc"}:
                    raise MediaError("Color range must be Auto, tv, or pc.")
                cmd += ["-color_range", color_range]
        audio_bitrate = _parse_bitrate(options.get("audio_bitrate", ""))
        if audio_bitrate and acodec_choice not in {"copy", "flac", "pcm", "alac"}:
            cmd += ["-b:a", audio_bitrate]
        fps = str(options.get("fps") or "Source").strip()
        fps_is_source = fps.casefold() in {"source", "vfr", "variable"}
        if not fps_is_source:
            try:
                fps_val = float(fps)
                if not 1 <= fps_val <= 240:
                    raise ValueError()
            except ValueError as exc:
                raise MediaError("FPS must be Source or a number between 1 and 240.") from exc
            cmd += ["-r", fps]
        frame_mode = str(options.get("fps_mode") or "CFR").upper()
        if frame_mode not in {"CFR", "VFR"}:
            raise MediaError("Frame mode must be CFR or VFR.")
        # Frame mode is independent of the numeric frame-rate control. In the
        # old implementation VFR was only sent when a numeric FPS was present,
        # so choosing Source + VFR silently did nothing.
        if not is_audio and vcodec_choice != "copy":
            cmd += ["-fps_mode", frame_mode.lower()]
        resolution = str(options.get("resolution") or "Source")
        if not options.get("custom_scale") and resolution != "Source" and resolution.endswith("p"):
            try:
                height = int(resolution[:-1])
            except ValueError as exc:
                raise MediaError(f"Invalid resolution: {resolution}") from exc
            cmd += ["-vf", f"scale=-2:{height}"]
        elif resolution not in {"Source", "Custom"}:
            raise MediaError(f"Invalid resolution: {resolution}")
        if resolution == "Custom" and not options.get("custom_scale"):
            raise MediaError("Enter a custom resolution such as 1920x1080.")
        if options.get("custom_scale"):
            custom = str(options["custom_scale"]).lower().replace(" ", "")
            if not re.fullmatch(r"\d{2,5}x\d{2,5}", custom):
                raise MediaError("Custom resolution must look like 1920x1080.")
            width, height = custom.split("x")
            cmd += ["-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"]
    # Audio stream controls apply to both audio-only output and video files
    # carrying an audio stream. Keeping them outside the audio/video branch
    # avoids the previous bug where only audio-only exports honoured them.
    sample_rate = str(options.get("sample_rate") or "").strip()
    if sample_rate and sample_rate != "Source":
        if not sample_rate.isdigit() or not (8000 <= int(sample_rate) <= 384000):
            raise MediaError("Sample rate must be between 8000 and 384000 Hz.")
        cmd += ["-ar", sample_rate]
    channels = str(options.get("channels") or "Source")
    if channels in {"Mono", "Stereo"}:
        cmd += ["-ac", "1" if channels == "Mono" else "2"]
    if options.get("preserve_metadata", True):
        cmd += ["-map_metadata", "0", "-map_chapters", "0"]
    if options.get("embed_subtitles") and subtitle_files and not is_audio:
        for idx, _sub in enumerate(subtitle_files, start=1):
            cmd += ["-map", f"{idx}:0?"]
        subtitle_codec = (
            "mov_text" if container in {"mp4", "m4v", "mov", "3gp"}
            else "webvtt" if container == "webm"
            else "copy"
        )
        cmd += ["-c:s", subtitle_codec]
    cmd += ["-movflags", "+faststart"] if container in {"mp4", "m4v", "mov"} else []
    cmd += ["-progress", "pipe:1", "-nostats", str(target)]
    return cmd


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _run_ffmpeg(source: Path, target: Path, options: dict, ffmpeg: str,
                cancel_event=None, progress_cb=None, duration=None, subtitle_files=None):
    options = dict(options)
    if not options.get("_available_encoders"):
        options["_available_encoders"] = list_encoders(ffmpeg)  # cached after first probe
    args = [ffmpeg] + _ffmpeg_args(source, target, options, subtitle_files)
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", bufsize=1, **_NO_WINDOW)
    except OSError as exc:
        raise MediaError(f"Could not start FFmpeg: {exc}") from exc

    # stderr is drained continuously: reading it only after stdout closed could
    # deadlock FFmpeg once the OS pipe buffer filled up.
    stderr_tail: deque[str] = deque(maxlen=40)

    def drain_stderr():
        try:
            for line in proc.stderr:  # type: ignore[union-attr]
                stderr_tail.append(line.rstrip())
        except (OSError, ValueError):
            pass

    # Cancellation is polled independently of FFmpeg output, so Cancel responds
    # within ~250 ms even when FFmpeg is silent (e.g. slow seeks, stalled input).
    def watch_cancel():
        while proc.poll() is None:
            if cancel_event.wait(0.25):  # type: ignore[union-attr]
                _terminate(proc)
                return

    helpers = [threading.Thread(target=drain_stderr, daemon=True)]
    if cancel_event is not None:
        helpers.append(threading.Thread(target=watch_cancel, daemon=True))
    for helper in helpers:
        helper.start()

    last_pct = -1
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.strip()
            if line.startswith("out_time_ms=") and duration:
                try:
                    elapsed = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                pct = max(0, min(99, int(elapsed / max(duration, 0.001) * 100)))
                if progress_cb and pct != last_pct:
                    progress_cb(pct, "Encoding…")
                    last_pct = pct
            elif line == "progress=end" and progress_cb:
                progress_cb(100, "Validating output…")
        return_code = proc.wait()
        for helper in helpers:
            helper.join(timeout=2)
        _check_cancel(cancel_event)
        if return_code != 0:
            raise MediaError(f"FFmpeg failed (exit {return_code}):\n" + "\n".join(stderr_tail)[-2200:])
    finally:
        _terminate(proc)


def _source_stream_codecs(source: Path, ffprobe: Optional[str]) -> Optional[dict]:
    """Return first audio/video codecs; absent keys mean that stream type is absent."""
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "stream=codec_type,codec_name", "-of", "json", str(source)],
            capture_output=True, text=True, timeout=12, **_NO_WINDOW,
        )
        if proc.returncode != 0:
            return None
        streams = json.loads(proc.stdout or "{}").get("streams") or []
        result = {}
        for stream in streams:
            kind = str(stream.get("codec_type") or "").lower()
            if kind in {"video", "audio"} and kind not in result:
                # Keep an empty codec name as "present but unknown". That is
                # different from a media file which genuinely has no such stream.
                result[kind] = str(stream.get("codec_name") or "").lower()
        return result
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return None


def _normalise_webm_options(source: Path, options: dict, ffprobe: Optional[str],
                            ffmpeg: str, log_cb=None, force_reencode: bool = False) -> dict:
    """Choose only WebM-safe codecs, retaining copy only after a successful probe.

    force_reencode is the recovery path for source files whose codec tags still
    fail the WebM muxer's final validation despite an initial successful probe.
    """
    adjusted = dict(options or {})
    if force_reencode:
        adjusted.update({
            "video_codec": "vp9",
            "audio_codec": "opus",
            "video_encoder": "Auto",
            "profile": "",
            "level": "",
            "rate_control": "CRF",
            "crf": "32",
            "video_bitrate": "",
            "pixel_format": "yuv420p",
            "embed_subtitles": False,
        })
        adjusted.pop("_webm_video_copy_safe", None)
        adjusted.pop("_webm_audio_copy_safe", None)
    codecs = _source_stream_codecs(source, ffprobe)
    video_choice = str(adjusted.get("video_codec") or "copy").lower()
    audio_choice = str(adjusted.get("audio_codec") or "copy").lower()
    video_allowed = {"vp8", "vp9", "av1"}
    audio_allowed = {"opus", "vorbis"}
    video_encoders = {
        "vp9": {"libvpx-vp9"},
        "vp8": {"libvpx"},
        "av1": {"libsvtav1", "libaom-av1", "av1_nvenc"},
    }
    audio_encoders = {"opus": "libopus", "vorbis": "libvorbis"}
    available = set(list_encoders(ffmpeg))
    changes = []

    # Probe failure or an unknown codec is never treated as proof that copy is safe.
    if video_choice == "copy":
        source_video = (codecs or {}).get("video")
        has_video = codecs is not None and "video" in codecs
        needs_video_encode = codecs is None or (
            has_video and source_video not in video_allowed
        )
        video_copy_safe = codecs is not None and (
            not has_video or source_video in video_allowed
        )
    else:
        needs_video_encode = video_choice not in video_allowed
        video_copy_safe = False

    video_encoder = str(adjusted.get("video_encoder") or "Auto")
    if video_choice in video_allowed:
        compatible = video_encoders[video_choice]
        if video_encoder != "Auto" and video_encoder not in compatible:
            adjusted["video_encoder"] = "Auto"
            adjusted["profile"] = ""
            adjusted["level"] = ""
            video_encoder = "Auto"
            changes.append("video encoder → Auto")
        if video_choice != "copy" and available and not (compatible & available):
            needs_video_encode = True
    elif video_choice == "copy" and video_encoder != "Auto":
        adjusted["video_encoder"] = "Auto"
        changes.append("video encoder → Auto")

    if needs_video_encode:
        candidates = [
            ("vp9", "libvpx-vp9"),
            ("vp8", "libvpx"),
            ("av1", "libsvtav1"),
            ("av1", "libaom-av1"),
            ("av1", "av1_nvenc"),
        ]
        chosen = next(
            ((codec, encoder) for codec, encoder in candidates if not available or encoder in available),
            None,
        )
        if not chosen:
            raise MediaError(
                "WebM output needs a VP8, VP9, or AV1 encoder. "
                "Install an FFmpeg build with libvpx-vp9 (recommended), libvpx, or libaom-av1."
            )
        video_choice, _encoder = chosen
        adjusted["video_codec"] = video_choice
        adjusted["video_encoder"] = "Auto"
        adjusted["profile"] = ""
        adjusted["level"] = ""
        rate_control = str(adjusted.get("rate_control") or "Source").upper()
        if rate_control not in {"CRF", "CQ", "CBR", "VBR"}:
            adjusted["rate_control"] = "CRF"
            adjusted["crf"] = "32"
            adjusted["video_bitrate"] = ""
        video_copy_safe = False
        changes.append(f"video → {video_choice.upper()}")

    if audio_choice == "copy":
        source_audio = (codecs or {}).get("audio")
        has_audio = codecs is not None and "audio" in codecs
        needs_audio_encode = codecs is None or (
            has_audio and source_audio not in audio_allowed
        )
        audio_copy_safe = codecs is not None and (
            not has_audio or source_audio in audio_allowed
        )
    else:
        needs_audio_encode = audio_choice not in audio_allowed
        audio_copy_safe = False

    if audio_choice in audio_allowed and available:
        if audio_encoders[audio_choice] not in available and audio_choice != "copy":
            needs_audio_encode = True

    if needs_audio_encode:
        candidates = ["opus", "vorbis"]
        audio_choice = next(
            (codec for codec in candidates if not available or audio_encoders[codec] in available),
            None,
        )
        if not audio_choice:
            raise MediaError(
                "WebM output needs an Opus or Vorbis audio encoder. "
                "Install an FFmpeg build with libopus or libvorbis."
            )
        adjusted["audio_codec"] = audio_choice
        audio_copy_safe = False
        changes.append(f"audio → {audio_choice.upper()}")

    # WebVTT is the only subtitle format accepted by FFmpeg's WebM muxer. yt-dlp
    # can supply SRT/ASS/TTML sidecars as well, so do not put them in the mux.
    # _finalize preserves downloaded subtitle files next to the WebM output.
    if adjusted.get("embed_subtitles"):
        adjusted["embed_subtitles"] = False
        changes.append("subtitle embedding → sidecar files")

    adjusted["_webm_video_copy_safe"] = bool(video_copy_safe)
    adjusted["_webm_audio_copy_safe"] = bool(audio_copy_safe)
    if log_cb:
        probed = ", ".join(f"{kind}={codec or 'unknown'}" for kind, codec in (codecs or {}).items()) or "probe unavailable"
        selected = (
            f"video={adjusted.get('video_codec', 'copy')}, "
            f"audio={adjusted.get('audio_codec', 'copy')}"
        )
        if changes:
            log_cb("WebM compatibility: " + ", ".join(changes) + ".")
        log_cb(f"WebM stream check: source [{probed}] → output [{selected}].")
    return adjusted


def _probe(path: Path, ffprobe: Optional[str]) -> dict:
    if not ffprobe:
        return {"validated": False, "message": "ffprobe not found; output received a basic file-size check only."}
    try:
        p = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate",
             "-of", "json", str(path)], capture_output=True, text=True, timeout=30, **_NO_WINDOW,
        )
        if p.returncode != 0:
            raise MediaError(f"Output validation failed: {(p.stderr or '').strip()[-1200:]}")
        data = json.loads(p.stdout or "{}")
        if not data.get("streams"):
            raise MediaError("Output validation failed: no playable audio/video streams were found.")
        return {"validated": True, "probe": data, "message": "Output validated with ffprobe."}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise MediaError(f"Could not validate output: {exc}") from exc


def _validate_webm_streams(validation: dict) -> None:
    """Reject any WebM file whose probed streams violate the muxer codec rules."""
    if not validation.get("validated"):
        return
    streams = (validation.get("probe") or {}).get("streams") or []
    allowed = {
        "video": {"vp8", "vp9", "av1"},
        "audio": {"opus", "vorbis"},
        "subtitle": {"webvtt"},
    }
    for stream in streams:
        kind = str(stream.get("codec_type") or "").lower()
        codec = str(stream.get("codec_name") or "").lower()
        if kind not in allowed or codec not in allowed[kind]:
            raise MediaError(
                f"WebM output contains an incompatible {kind or 'unknown'} stream "
                f"({codec or 'unknown codec'}). Select a WebM-compatible profile or use MKV/MP4."
            )


def _finalize(source: Path, output_dir: Path, options: dict, job_id: str, ffmpeg_path=None,
              ffprobe_path=None, cancel_event=None, progress_cb=None, subtitle_files=None,
              log_cb=None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    container = (options.get("container") or "original").lower()
    audio_only = container in AUDIO_CONTAINERS or bool(options.get("audio_only"))
    suffix = source.suffix.lower()
    if container != "original":
        suffix = "." + container
    elif suffix not in MEDIA_EXTENSIONS:
        suffix = ".mkv"
    stem = _safe_stem(source.stem)
    target = _unique_path(output_dir / f"{stem}{suffix}")
    ffmpeg = _which("ffmpeg", ffmpeg_path)
    ffprobe = _which("ffprobe", ffprobe_path)
    options = dict(options or {})
    # "Original" is a user-facing selection, not a muxer. Detect the actual
    # output container from the final filename too: a downloaded .webm source
    # can still need a re-encode/remux, and it must receive the same codec
    # validation/recovery as an explicitly selected WebM output.
    is_webm_output = suffix.casefold() == ".webm"
    if is_webm_output:
        options["container"] = "webm"
    wants_edit = (
        container != "original" or
        (options.get("video_codec", "copy").lower() != "copy" and not audio_only) or
        (options.get("audio_codec", "copy").lower() != "copy") or
        options.get("fps", "Source") != "Source" or
        options.get("resolution", "Source") != "Source" or
        bool(options.get("custom_scale")) or
        bool(options.get("embed_subtitles"))
    )
    if is_webm_output and wants_edit:
        if not ffmpeg:
            raise MediaError("FFmpeg is required to create or edit WebM output. Install FFmpeg and make sure ffmpeg is on PATH.")
        options = _normalise_webm_options(source, options, ffprobe, ffmpeg, log_cb)
    if not wants_edit:
        _check_cancel(cancel_event)
        shutil.move(str(source), str(target))
        if progress_cb:
            progress_cb(100, "Validating output…")
    else:
        if not ffmpeg:
            raise MediaError("FFmpeg is required for conversion/remuxing. Install FFmpeg and make sure ffmpeg is on PATH.")
        # Keep source duration when known so the FFmpeg progress bar can be meaningful.
        duration = None
        if ffprobe:
            try:
                p = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)], capture_output=True, text=True, timeout=10, **_NO_WINDOW)
                duration = float(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else None
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                _LOG.debug("Could not probe source duration for %s: %s", source, exc)
                duration = None
        processing = target.with_name(target.stem + ".processing" + target.suffix)
        try:
            try:
                _run_ffmpeg(source, processing, options, ffmpeg, cancel_event, progress_cb, duration, subtitle_files)
            except MediaError as first_error:
                error_text = str(first_error).casefold()
                webm_muxer_rejected_codecs = (
                    is_webm_output
                    and (
                        "only vp8 or vp9 or av1 video" in error_text
                        or (
                            "could not write header" in error_text
                            and "invalid argument" in error_text
                        )
                    )
                )
                if not webm_muxer_rejected_codecs:
                    raise
                if log_cb:
                    log_cb(
                        "The WebM muxer rejected the selected stream combination; "
                        "retrying with WebM-safe VP9/Opus encoding."
                    )
                processing.unlink(missing_ok=True)
                options = _normalise_webm_options(
                    source, options, ffprobe, ffmpeg, log_cb, force_reencode=True
                )
                _run_ffmpeg(
                    source, processing, options, ffmpeg,
                    cancel_event, progress_cb, duration, subtitle_files,
                )
            if not processing.exists() or processing.stat().st_size == 0:
                raise MediaError("FFmpeg did not produce a non-empty output file.")
            processing.replace(target)
        finally:
            if processing.exists():
                processing.unlink(missing_ok=True)
    if not target.exists() or target.stat().st_size == 0:
        raise MediaError("The output file is missing or empty.")
    validation = _probe(target, ffprobe)
    if is_webm_output:
        try:
            _validate_webm_streams(validation)
        except MediaError:
            target.unlink(missing_ok=True)
            raise
    # Preserve subtitle sidecars when the user asked to download, but not embed, them.
    if subtitle_files and not options.get("embed_subtitles"):
        for sub in subtitle_files:
            try:
                shutil.copy2(sub, _unique_path(output_dir / f"{target.stem}.{sub.suffix.lstrip('.')}"))
            except OSError as exc:
                if log_cb:
                    log_cb(f"Could not preserve subtitle sidecar {sub.name}: {exc}")
    if progress_cb:
        progress_cb(100, validation["message"])
    return target


def _scan_work_dir(folder: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """One directory walk returning (media, subtitles, thumbnails).

    Previously the work folder was walked three or four times per download.
    """
    media: list[tuple[float, str, Path]] = []
    subtitles: list[Path] = []
    thumbnails: list[Path] = []
    for p in folder.rglob("*"):
        if not p.is_file():
            continue
        suffix = p.suffix.lower()
        if suffix in MEDIA_EXTENSIONS:
            if ".processing" in p.name:
                continue
            try:
                media.append((p.stat().st_mtime, p.name, p))
            except OSError:
                continue
        elif suffix in SUBTITLE_EXTENSIONS:
            subtitles.append(p)
        elif suffix in THUMBNAIL_EXTENSIONS:
            thumbnails.append(p)
    media.sort()
    return [item[2] for item in media], subtitles, thumbnails


def _collect_media_files(folder: Path) -> list[Path]:
    return _scan_work_dir(folder)[0]


def download_and_process(url: str, output_dir: str, options: dict, job_id: str,
                         cancel_event=None, progress_cb=None, log_cb=None,
                         ffmpeg_path=None, ffprobe_path=None, settings=None) -> list[Path]:
    url = str(url or "").strip()
    _check_cancel(cancel_event)
    if not is_http_url(url):
        raise MediaError("Enter a valid absolute http:// or https:// media URL with a hostname.")
    try:
        import yt_dlp
    except ImportError as exc:
        raise MediaError("yt-dlp is missing. Run the installer script or: pip install -r requirements.txt") from exc
    work_dir = APP_DIR / "work" / job_id
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    output = Path(output_dir).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    settings = settings or {}
    last_report = {"pct": -1, "t": 0.0}

    def hook(data):
        _check_cancel(cancel_event)
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            got = data.get("downloaded_bytes") or 0
            pct = int(got * 100 / total) if total else 0
            speed = data.get("speed")
            eta = data.get("eta")
            label = "Downloading"
            if speed:
                label += f" · {speed / 1024 / 1024:.2f} MB/s"
            if eta is not None:
                label += f" · ETA {eta}s"
            if progress_cb:
                # yt-dlp fires this hook many times per second; only forward a
                # change in percentage or a label refresh at most once per second.
                value = min(68, int(pct * 0.68))
                now = time.monotonic()
                if value != last_report["pct"] or now - last_report["t"] >= 1.0:
                    last_report.update(pct=value, t=now)
                    progress_cb(value, label)
        elif status == "finished":
            if progress_cb:
                progress_cb(70, "Download finished · preparing media…")
        elif status == "error" and log_cb:
            log_cb(str(data.get("filename", "Download error")))

    subtitle_langs = options.get("subtitle_languages") or settings.get("subtitle_languages") or ["all"]
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": False,
        "noplaylist": False,
        "windowsfilenames": True,
        "retries": int(settings.get("max_retries", 3)),
        "fragment_retries": int(settings.get("max_retries", 3)),
        "concurrent_fragment_downloads": int(settings.get("fragment_concurrency", 4)),
        "socket_timeout": 30,
        "continuedl": True,
        "overwrites": False,
        "outtmpl": str(work_dir / "%(title).180B [%(id)s].%(ext)s"),
        "format": options.get("format") or "bestvideo+bestaudio/best",
        "progress_hooks": [hook],
        "writesubtitles": bool(options.get("write_subtitles") or options.get("embed_subtitles")),
        "writeautomaticsub": bool(options.get("write_automatic_subtitles", settings.get("write_automatic_subtitles", False))),
        "subtitleslangs": subtitle_langs,
        "subtitlesformat": "srt/best",
        "writethumbnail": bool(options.get("download_thumbnail")),
        "writeinfojson": False,
    }
    # Respect the user connection and browser-session preferences.
    ydl_opts.update(network_options(settings))
    # Without this, a custom FFmpeg path from Settings was ignored by yt-dlp and
    # separate video+audio streams could not be merged.
    if ffmpeg_path and Path(ffmpeg_path).expanduser().is_file():
        ydl_opts["ffmpeg_location"] = str(Path(ffmpeg_path).expanduser())
    if log_cb:
        log_cb("Starting yt-dlp. Downloads are processed locally.")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except CancelledError:
        shutil.rmtree(work_dir, ignore_errors=True)  # don't leak partial downloads on cancel
        raise
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise MediaError(f"yt-dlp download failed: {exc}") from exc
    try:
        _check_cancel(cancel_event)
    except CancelledError:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    media_files, subtitle_files, thumbnail_files = _scan_work_dir(work_dir)
    if not media_files:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise MediaError("yt-dlp finished but no media file was found. The URL may be unsupported, unavailable, or protected.")
    results = []
    total = len(media_files)
    for index, source in enumerate(media_files, start=1):
        try:
            _check_cancel(cancel_event)
        except CancelledError:
            # Cancellation between playlist items must not leave the remaining
            # downloaded fragments, subtitles, or thumbnails in the work tree.
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        start = 70 + int((index - 1) / total * 25)
        def finalize_progress(pct, label):
            if progress_cb:
                progress_cb(start + int(max(0, min(100, pct)) * 0.25), f"{label} · item {index}/{total}")
        if log_cb:
            log_cb(f"Finalizing {source.name}")
        # yt-dlp names sidecars "<media stem>.<lang>.<ext>". The old exact-stem test
        # never matched, so every playlist item received *all* subtitle files.
        prefix = source.stem + "."
        matching_subtitles = [p for p in subtitle_files if p.name.startswith(prefix)]
        if not matching_subtitles and total == 1:
            matching_subtitles = subtitle_files
        try:
            target = _finalize(source, output, options, f"{job_id}-{index}", ffmpeg_path,
                               ffprobe_path, cancel_event, finalize_progress, matching_subtitles, log_cb)
        except Exception:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        if options.get("download_thumbnail"):
            # Path.glob(stem + ".*") treated the "[video-id]" in the stem as a
            # character class and never found the thumbnail.
            for thumb in (p for p in thumbnail_files if p.stem == source.stem):
                try:
                    shutil.copy2(thumb, _unique_path(output / f"{target.stem}{thumb.suffix.lower()}"))
                except OSError:
                    pass
        results.append(target)
        if log_cb:
            log_cb(f"Saved: {target}")
    shutil.rmtree(work_dir, ignore_errors=True)
    if progress_cb:
        progress_cb(100, f"Completed · {len(results)} file(s)")
    return results


def convert_file(source_path: str, output_dir: str, options: dict, job_id: str,
                 cancel_event=None, progress_cb=None, log_cb=None,
                 ffmpeg_path=None, ffprobe_path=None) -> Path:
    source = Path(source_path).expanduser()
    if not source.is_file():
        raise MediaError(f"Input file does not exist: {source}")
    if source.suffix.lower() not in MEDIA_EXTENSIONS:
        raise MediaError(f"Unsupported input extension: {source.suffix}")
    _check_cancel(cancel_event)
    if log_cb:
        log_cb(f"Converting {source.name}")
    target = _finalize(source, Path(output_dir).expanduser(), options, job_id,
                       ffmpeg_path, ffprobe_path, cancel_event, progress_cb, log_cb=log_cb)
    if log_cb:
        log_cb(f"Saved: {target}")
    return target
