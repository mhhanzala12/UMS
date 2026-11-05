"""Local application configuration."""
from __future__ import annotations

import json
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
    "subtitle_languages": ["all"],
    "connection_mode": "Automatic",
    "proxy_url": "",
    "cookies_browser": "None",
    "cookies_profile": "",
    "player_volume": 0.75,
    "player_muted": False,
}


def load_settings() -> dict:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**DEFAULT_SETTINGS, **data}
        except (OSError, json.JSONDecodeError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
