"""Local application configuration."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

APP_DIR = Path.home() / ".universal_media_studio"
CONFIG_FILE = APP_DIR / "settings.json"
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
    "player_volume": 0.75,
    "player_muted": False,
}

# Settings are read/written from the GUI thread *and* worker threads
# (playlists), so file access is serialised.
_IO_LOCK = threading.RLock()


def load_settings() -> dict:
    with _IO_LOCK:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {**DEFAULT_SETTINGS, **data}
            except (OSError, json.JSONDecodeError):
                pass
        return dict(DEFAULT_SETTINGS)


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


def save_settings(settings: dict) -> None:
    with _IO_LOCK:
        atomic_write_text(CONFIG_FILE, json.dumps(settings, indent=2, ensure_ascii=False))


def update_settings(**changes) -> dict:
    """Read-modify-write only the given keys, so unrelated keys written by
    other code paths (e.g. playlists) are never clobbered by a stale copy."""
    with _IO_LOCK:
        current = load_settings()
        current.update(changes)
        save_settings(current)
        return current
