"""yt-dlp + FFmpeg media engine. All processing happens locally."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .config import APP_DIR

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


def _which(name: str, configured: Optional[str] = None) -> Optional[str]:
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return str(p)
    return shutil.which(name)


def tool_status(ffmpeg_path: Optional[str] = None, ffprobe_path: Optional[str] = None) -> dict:
    try:
        import yt_dlp
        ytdlp_version = getattr(yt_dlp, "__version__", "installed")
    except Exception:
        ytdlp_version = None
    ffmpeg = _which("ffmpeg", ffmpeg_path)
    ffprobe = _which("ffprobe", ffprobe_path)
    ffmpeg_version = None
    encoders = []
    if ffmpeg:
        try:
            p = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=5)
            first = (p.stdout or p.stderr).splitlines()[0]
            ffmpeg_version = first[:120]
        except Exception:
            ffmpeg_version = "Found (version check failed)"
        try:
            p = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=12)
            for line in (p.stdout + "\n" + p.stderr).splitlines():
                match = re.match(r"^\s*[VASD.]{6}\s+(\S+)", line)
                if match and match.group(1) != "=":
                    encoders.append(match.group(1))
        except Exception:
            encoders = []
    return {
        "yt_dlp": ytdlp_version,
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "ffmpeg_version": ffmpeg_version,
        "encoders": sorted(set(encoders)),
    }


def analyze_url(url: str, cancel_event: Optional[threading.Event] = None, settings: Optional[dict] = None) -> dict:
    """Fetch metadata and source formats without downloading media."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise MediaError("yt-dlp is missing. Run the installer script or: pip install -r requirements.txt") from exc
    url = url.strip()
    if not url:
        raise MediaError("Paste a media URL first.")
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
    settings = settings or {}
    mode = str(settings.get("connection_mode") or "Automatic").lower()
    if mode == "direct":
        opts["proxy"] = ""
    elif mode == "proxy":
        proxy = str(settings.get("proxy_url") or "").strip()
        if not proxy:
            raise MediaError("Proxy mode is selected, but no proxy URL is configured.")
        opts["proxy"] = proxy
    browser = str(settings.get("cookies_browser") or "None").strip().lower()
    profile = str(settings.get("cookies_profile") or "").strip()
    if browser in {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale"}:
        opts["cookiesfrombrowser"] = (browser, profile or None)
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
        height = f.get("height")
        fps = f.get("fps")
        size = f.get("filesize") or f.get("filesize_approx")
        formats.append({
            "format_id": str(f.get("format_id", "?")),
            "ext": str(f.get("ext", "?")),
            "resolution": f.get("resolution") or (f"{height}p" if height else "audio / unknown"),
            "height": height,
            "fps": fps,
            "vcodec": f.get("vcodec"),
            "acodec": f.get("acodec"),
            "filesize": size,
            "note": f.get("format_note") or "",
            "format": f.get("format") or "",
        })
    formats.sort(key=lambda x: (x.get("height") or 0, x.get("fps") or 0, x["format_id"]))
    return {
        "title": info.get("title") or "Untitled media",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader") or info.get("channel") or "",
        "webpage_url": info.get("webpage_url") or url,
        "formats": formats,
        "subtitles": sorted((info.get("subtitles") or {}).keys()),
        "automatic_captions": sorted((info.get("automatic_captions") or {}).keys()),
        "is_live": bool(info.get("is_live")),
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
    encoder_preferences = {
        "h264": ["libx264", "h264_nvenc", "h264_qsv", "h264_amf"],
        "h.264": ["libx264", "h264_nvenc", "h264_qsv", "h264_amf"],
        "hevc": ["libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf"],
        "h265": ["libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf"],
        "av1": ["libsvtav1", "libaom-av1", "av1_nvenc"],
        "vp9": ["libvpx-vp9"], "vp8": ["libvpx"],
        "mpeg4": ["mpeg4"], "mpeg2": ["mpeg2video"], "theora": ["libtheora"],
    }
    def preferred_encoder(codec, default):
        candidates = encoder_preferences.get(codec, [default])
        if not available:
            return default
        return next((item for item in candidates if item in available), default)
    vmap = {
        "h264": preferred_encoder("h264", "libx264"), "h.264": preferred_encoder("h.264", "libx264"),
        "hevc": preferred_encoder("hevc", "libx265"), "h265": preferred_encoder("h265", "libx265"),
        "av1": preferred_encoder("av1", "libsvtav1"),
        "vp9": preferred_encoder("vp9", "libvpx-vp9"), "vp8": preferred_encoder("vp8", "libvpx"),
        "mpeg4": "mpeg4", "mpeg2": "mpeg2video", "theora": "libtheora", "copy": "copy",
    }
    encoder_families = {
        "h264": {"libx264", "h264_nvenc", "h264_qsv", "h264_amf"},
        "h.264": {"libx264", "h264_nvenc", "h264_qsv", "h264_amf"},
        "hevc": {"libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf"},
        "h265": {"libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf"},
        "av1": {"libsvtav1", "libaom-av1", "av1_nvenc"},
        "vp9": {"libvpx-vp9"}, "vp8": {"libvpx"},
        "mpeg4": {"mpeg4"}, "mpeg2": {"mpeg2video"}, "theora": {"libtheora"},
    }
    encoder_override = str(options.get("video_encoder") or "Auto")
    if encoder_override != "Auto":
        if vcodec_choice == "copy" or encoder_override not in encoder_families.get(vcodec_choice, set()):
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

    cmd = ["-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
    subtitle_files = list(subtitle_files or [])
    if options.get("embed_subtitles") and not is_audio:
        for sub in subtitle_files:
            cmd += ["-i", str(sub)]
    if is_audio:
        cmd += ["-vn", "-map", "0:a:0?"]
        cmd += ["-c:a", amap.get(acodec_choice, "copy")]
        audio_bitrate = _parse_bitrate(options.get("audio_bitrate", ""))
        if audio_bitrate and acodec_choice not in {"copy", "flac", "pcm", "alac"}:
            cmd += ["-b:a", audio_bitrate]
        sample_rate = str(options.get("sample_rate") or "").strip()
        if sample_rate and sample_rate != "Source":
            if not sample_rate.isdigit() or not (8000 <= int(sample_rate) <= 384000):
                raise MediaError("Sample rate must be between 8000 and 384000 Hz.")
            cmd += ["-ar", sample_rate]
        channels = str(options.get("channels") or "Source")
        if channels in {"Mono", "Stereo"}:
            cmd += ["-ac", "1" if channels == "Mono" else "2"]
    else:
        cmd += ["-map", "0:v:0?", "-map", "0:a:0?"]
        cmd += ["-c:v", vmap[vcodec_choice]]
        cmd += ["-c:a", amap[acodec_choice]]
        if vcodec_choice != "copy":
            rate_control = (options.get("rate_control") or "CRF").upper()
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
                elif rate_control == "CQ" and encoder in {"libvpx", "libvpx-vp9"}:
                    cmd += ["-b:v", "0", "-crf", crf]
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
            elif encoder in {"libx264", "libx265", "libvpx", "libvpx-vp9", "h264_qsv", "hevc_qsv"}:
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
        if fps.lower() not in {"source", "vfr", "variable"}:
            try:
                fps_val = float(fps)
                if not 1 <= fps_val <= 240:
                    raise ValueError()
            except ValueError as exc:
                raise MediaError("FPS must be Source/VFR or a number between 1 and 240.") from exc
            cmd += ["-r", fps]
            if options.get("fps_mode") == "VFR":
                cmd += ["-fps_mode", "vfr"]
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
    if options.get("preserve_metadata", True):
        cmd += ["-map_metadata", "0", "-map_chapters", "0"]
    if options.get("embed_subtitles") and subtitle_files and not is_audio:
        for idx, _sub in enumerate(subtitle_files, start=1):
            cmd += ["-map", f"{idx}:0?"]
        subtitle_codec = "mov_text" if container in {"mp4", "m4v", "mov", "3gp"} else "copy"
        cmd += ["-c:s", subtitle_codec]
    cmd += ["-movflags", "+faststart"] if container in {"mp4", "m4v", "mov"} else []
    cmd += ["-progress", "pipe:1", "-nostats", str(target)]
    return cmd


def _run_ffmpeg(source: Path, target: Path, options: dict, ffmpeg: str,
                cancel_event=None, progress_cb=None, duration=None, subtitle_files=None):
    options = dict(options)
    if not options.get("_available_encoders"):
        try:
            probe = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=12)
            options["_available_encoders"] = [
                match.group(1) for line in (probe.stdout + "\n" + probe.stderr).splitlines()
                if (match := re.match(r"^\s*[VASD.]{6}\s+(\S+)", line)) and match.group(1) != "="
            ]
        except Exception:
            options["_available_encoders"] = []
    args = [ffmpeg] + _ffmpeg_args(source, target, options, subtitle_files)
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
    except OSError as exc:
        raise MediaError(f"Could not start FFmpeg: {exc}") from exc
    last_pct = -1
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            _check_cancel(cancel_event)
            line = raw.strip()
            if line.startswith("out_time_ms=") and duration:
                try:
                    elapsed = int(line.split("=", 1)[1]) / 1_000_000
                    pct = max(0, min(99, int(elapsed / max(duration, 0.001) * 100)))
                    if progress_cb and pct != last_pct:
                        progress_cb(pct, "Encoding…")
                        last_pct = pct
                except ValueError:
                    pass
            elif line == "progress=end" and progress_cb:
                progress_cb(100, "Validating output…")
        return_code = proc.wait()
        stderr = proc.stderr.read() if proc.stderr else ""
        if return_code != 0:
            raise MediaError(f"FFmpeg failed (exit {return_code}):\n{stderr[-2200:]}")
    except CancelledError:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        raise
    except Exception:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        raise


def _probe(path: Path, ffprobe: Optional[str]) -> dict:
    if not ffprobe:
        return {"validated": False, "message": "ffprobe not found; output received a basic file-size check only."}
    try:
        p = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate",
             "-of", "json", str(path)], capture_output=True, text=True, timeout=30,
        )
        if p.returncode != 0:
            raise MediaError(f"Output validation failed: {(p.stderr or '').strip()[-1200:]}")
        data = json.loads(p.stdout or "{}")
        if not data.get("streams"):
            raise MediaError("Output validation failed: no playable audio/video streams were found.")
        return {"validated": True, "probe": data, "message": "Output validated with ffprobe."}
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise MediaError(f"Could not validate output: {exc}") from exc


def _finalize(source: Path, output_dir: Path, options: dict, job_id: str, ffmpeg_path=None,
              ffprobe_path=None, cancel_event=None, progress_cb=None, subtitle_files=None) -> Path:
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
    wants_edit = (
        container != "original" or
        (options.get("video_codec", "copy").lower() != "copy" and not audio_only) or
        (options.get("audio_codec", "copy").lower() != "copy") or
        options.get("fps", "Source") != "Source" or
        options.get("resolution", "Source") != "Source" or
        bool(options.get("custom_scale")) or
        bool(options.get("embed_subtitles"))
    )
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
                p = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)], capture_output=True, text=True, timeout=10)
                duration = float(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else None
            except Exception:
                duration = None
        processing = target.with_name(target.stem + ".processing" + target.suffix)
        try:
            _run_ffmpeg(source, processing, options, ffmpeg, cancel_event, progress_cb, duration, subtitle_files)
            if not processing.exists() or processing.stat().st_size == 0:
                raise MediaError("FFmpeg did not produce a non-empty output file.")
            processing.replace(target)
        finally:
            if processing.exists():
                processing.unlink(missing_ok=True)
    if not target.exists() or target.stat().st_size == 0:
        raise MediaError("The output file is missing or empty.")
    validation = _probe(target, ffprobe)
    # Preserve subtitle sidecars when the user asked to download, but not embed, them.
    if subtitle_files and not options.get("embed_subtitles"):
        for sub in subtitle_files:
            try:
                shutil.copy2(sub, _unique_path(output_dir / f"{target.stem}.{sub.suffix.lstrip('.')}"))
            except OSError:
                pass
    if progress_cb:
        progress_cb(100, validation["message"])
    return target


def _collect_media_files(folder: Path) -> list[Path]:
    found = []
    for p in folder.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        if p.name.endswith((".part", ".ytdl")) or ".processing" in p.name:
            continue
        found.append(p)
    return sorted(found, key=lambda p: p.stat().st_mtime)


def download_and_process(url: str, output_dir: str, options: dict, job_id: str,
                         cancel_event=None, progress_cb=None, log_cb=None,
                         ffmpeg_path=None, ffprobe_path=None, settings=None) -> list[Path]:
    try:
        import yt_dlp
    except ImportError as exc:
        raise MediaError("yt-dlp is missing. Run the installer script or: pip install -r requirements.txt") from exc
    _check_cancel(cancel_event)
    work_dir = APP_DIR / "work" / job_id
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    output = Path(output_dir).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    settings = settings or {}
    last_report = {"pct": -1}

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
                progress_cb(min(68, int(pct * 0.68)), label)
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
    connection_mode = str(settings.get("connection_mode") or "Automatic").lower()
    if connection_mode == "direct":
        ydl_opts["proxy"] = ""
    elif connection_mode == "proxy":
        proxy_url = str(settings.get("proxy_url") or "").strip()
        if proxy_url:
            ydl_opts["proxy"] = proxy_url
        else:
            raise MediaError("Proxy mode is selected, but no proxy URL is configured.")
    browser = str(settings.get("cookies_browser") or "").strip().lower()
    supported_browsers = {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale"}
    profile = str(settings.get("cookies_profile") or "").strip()
    if browser in supported_browsers and browser != "none":
        ydl_opts["cookiesfrombrowser"] = (browser, profile or None)
    if log_cb:
        log_cb("Starting yt-dlp. Downloads are processed locally.")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except CancelledError:
        raise
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise MediaError(f"yt-dlp download failed: {exc}") from exc
    try:
        _check_cancel(cancel_event)
    except CancelledError:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    media_files = _collect_media_files(work_dir)
    if not media_files:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise MediaError("yt-dlp finished but no media file was found. The URL may be unsupported, unavailable, or protected.")
    subtitle_files = [p for p in work_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".srt", ".vtt", ".ass", ".ssa", ".ttml"}]
    results = []
    total = len(media_files)
    for index, source in enumerate(media_files, start=1):
        _check_cancel(cancel_event)
        start = 70 + int((index - 1) / total * 25)
        def finalize_progress(pct, label):
            if progress_cb:
                progress_cb(start + int(max(0, min(100, pct)) * 0.25), f"{label} · item {index}/{total}")
        if log_cb:
            log_cb(f"Finalizing {source.name}")
        matching_subtitles = [p for p in subtitle_files if p.stem == source.stem] or subtitle_files
        try:
            target = _finalize(source, output, options, f"{job_id}-{index}", ffmpeg_path,
                               ffprobe_path, cancel_event, finalize_progress, matching_subtitles)
        except Exception:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        if options.get("download_thumbnail"):
            for thumb in work_dir.glob(source.stem + ".*"):
                if thumb.is_file() and thumb.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
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
                       ffmpeg_path, ffprobe_path, cancel_event, progress_cb)
    if log_cb:
        log_cb(f"Saved: {target}")
    return target
