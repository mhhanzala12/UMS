"""Local application configuration with defensive validation and atomic writes."""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

APP_DIR = Path.home() / ".universal_media_studio"
CONFIG_FILE = APP_DIR / "settings.json"
LOG_FILE = APP_DIR / "startup.log"
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3
DEFAULT_OUTPUT = Path.home() / "Downloads" / "UniversalMediaStudio"

DEFAULT_SETTINGS = {
    "output_dir": str(DEFAULT_OUTPUT),
    "theme": "Dark",
    "custom_presets": {},
    "max_retries": 3,
    "fragment_concurrency": 4,
    "write_automatic_subtitles": False,
    "download_lyrics": True,
    "subtitle_languages": ["all"],
    "connection_mode": "Automatic",
    "proxy_url": "",
    "cookies_browser": "None",
    "cookies_profile": "",
    "ffmpeg_path": "",
    "ffprobe_path": "",
    "player_volume": 0.75,
    "player_muted": False,
    "player_shuffle": False,
    "player_repeat": 0,
}

# Settings are read/written from the GUI thread and worker threads (playlists),
# so file access is serialised.
_IO_LOCK = threading.RLock()
_LOG = logging.getLogger(__name__)
_BROWSER_NAMES = {
    "none", "brave", "chrome", "chromium", "edge", "firefox", "opera",
    "safari", "vivaldi", "whale",
}


def configure_logging() -> Path | None:
    """Install a small rotating UTF-8 application log and return its path."""
    from logging.handlers import RotatingFileHandler

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        ))
        root = logging.getLogger()
        for existing in root.handlers[:]:
            root.removeHandler(existing)
            try:
                existing.close()
            except Exception:
                pass
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        logging.captureWarnings(True)
        _LOG.info("Application logging initialized: %s", LOG_FILE)
        return LOG_FILE
    except OSError:
        logging.basicConfig(level=logging.INFO, force=True)
        logging.exception("Could not initialize the application log file")
        return None


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        if isinstance(value, float) and not value.is_integer():
            return default
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if minimum <= number <= maximum else default


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number) or not minimum <= number <= maximum:
        return default
    return number


def _string(value: Any, default: str, limit: int = 4096) -> str:
    if not isinstance(value, str):
        return default
    value = value.strip()
    return value[:limit] if value else default


def _normalise_settings(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Merge defaults and repair invalid values without discarding future keys."""
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings.update(data)
    repaired: list[str] = []

    def repair(key: str, value: Any) -> None:
        if settings.get(key) != value:
            repaired.append(key)
        settings[key] = value

    repair("output_dir", _string(settings.get("output_dir"), DEFAULT_SETTINGS["output_dir"]))
    theme = _string(settings.get("theme"), "Dark", 16)
    repair("theme", theme if theme in {"Dark", "Light"} else "Dark")

    for key in ("proxy_url", "cookies_profile", "ffmpeg_path", "ffprobe_path"):
        repair(key, _string(settings.get(key), "", 4096) if isinstance(settings.get(key), str) else "")

    mode = _string(settings.get("connection_mode"), "Automatic", 24).casefold()
    repair("connection_mode", {"automatic": "Automatic", "proxy": "Proxy", "direct": "Direct"}.get(mode, "Automatic"))

    browser = _string(settings.get("cookies_browser"), "None", 24).casefold()
    # Persist the disabled choice with its public UI spelling ("None") rather
    # than briefly normalising it to lowercase and logging a false repair.
    browser_value = "None" if browser == "none" else (browser if browser in _BROWSER_NAMES else "None")
    repair("cookies_browser", browser_value)

    repair("max_retries", _bounded_int(settings.get("max_retries"), 3, 0, 10))
    repair("fragment_concurrency", _bounded_int(settings.get("fragment_concurrency"), 4, 1, 16))
    repair("player_repeat", _bounded_int(settings.get("player_repeat"), 0, 0, 2))
    repair("player_volume", _bounded_float(settings.get("player_volume"), 0.75, 0.0, 1.0))

    for key in ("write_automatic_subtitles", "download_lyrics", "player_muted", "player_shuffle"):
        value = settings.get(key)
        repair(key, value if isinstance(value, bool) else DEFAULT_SETTINGS[key])

    custom = settings.get("custom_presets")
    repair("custom_presets", dict(custom) if isinstance(custom, dict) else {})

    languages = settings.get("subtitle_languages")
    if isinstance(languages, list):
        languages = [item.strip()[:32] for item in languages if isinstance(item, str) and item.strip()][:30]
    else:
        languages = []
    repair("subtitle_languages", languages or ["all"])

    searches = settings.get("recent_searches", [])
    if isinstance(searches, list):
        searches = [item.strip()[:200] for item in searches if isinstance(item, str) and item.strip()][:8]
    else:
        searches = []
    if "recent_searches" in settings:
        repair("recent_searches", searches)

    # This key is owned by the music subsystem, but validate it here so an
    # invalid playlist value cannot break playback or JSON serialization.
    if "music_playlists" in settings:
        raw_playlists = settings.get("music_playlists")
        playlists: dict[str, list[str]] = {}
        if isinstance(raw_playlists, dict):
            for name, paths in raw_playlists.items():
                if isinstance(name, str) and isinstance(paths, list):
                    playlists[name[:100]] = [path for path in paths if isinstance(path, str) and path][:5000]
        repair("music_playlists", playlists)

    return settings, repaired


def load_settings() -> dict:
    with _IO_LOCK:
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            _LOG.exception("Could not create the settings directory; using defaults")
            return copy.deepcopy(DEFAULT_SETTINGS)

        if not CONFIG_FILE.exists():
            return copy.deepcopy(DEFAULT_SETTINGS)
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            _LOG.exception("Could not read settings.json; using safe defaults")
            return copy.deepcopy(DEFAULT_SETTINGS)
        if not isinstance(data, dict):
            _LOG.warning("settings.json must contain a JSON object; using safe defaults")
            return copy.deepcopy(DEFAULT_SETTINGS)

        settings, repaired = _normalise_settings(data)
        if repaired:
            _LOG.warning("Repaired invalid settings values: %s", ", ".join(sorted(set(repaired))))
        return settings


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file + rename so a crash can never leave a truncated file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def save_settings(settings: dict) -> dict:
    with _IO_LOCK:
        cleaned, repaired = _normalise_settings(settings if isinstance(settings, dict) else {})
        if repaired:
            _LOG.warning("Normalised invalid settings before saving: %s", ", ".join(sorted(set(repaired))))
        atomic_write_text(CONFIG_FILE, json.dumps(cleaned, indent=2, ensure_ascii=False))
        return cleaned


def update_settings(**changes) -> dict:
    """Read-modify-write only the given keys, so unrelated settings are preserved."""
    with _IO_LOCK:
        current = load_settings()
        current.update(changes)
        return save_settings(current)
