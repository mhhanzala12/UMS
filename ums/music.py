"""Music discovery, local library helpers, and credential-free audio matching.

Inspired by Unstream's music-first workflows. This module is adapted for the
native PySide6 application and keeps media processing on the user's machine.
"""
from __future__ import annotations

import json
import os
import re
import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, url2pathname, urlopen

from PySide6.QtCore import QThread, Signal

from .config import APP_DIR, atomic_write_text, load_settings, update_settings
from .lyrics import lyric_match_score, parse_lrc, parse_ttml
from .engine import CancelledError, network_options

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav", ".aiff", ".wma"}
MUSIC_LIBRARY_DIR = Path.home() / "Music" / "UniversalMediaStudio"
PLAYLISTS_KEY = "music_playlists"


_JSON_CACHE: dict[str, tuple[float, dict]] = {}
_JSON_CACHE_LOCK = threading.Lock()
_JSON_CACHE_TTL = 120.0
_JSON_CACHE_MAX = 96


def _get_json(url: str) -> dict:
    """GET + decode JSON with a short TTL cache.

    Re-opening an album, going back to a search, or re-running the same query
    no longer repeats identical Deezer/iTunes round-trips.
    """
    now = time.monotonic()
    with _JSON_CACHE_LOCK:
        hit = _JSON_CACHE.get(url)
        if hit and now - hit[0] < _JSON_CACHE_TTL:
            return hit[1]
    request = Request(url, headers={"User-Agent": "UniversalMediaStudio/1.0 (local desktop app)"})
    with urlopen(request, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
    with _JSON_CACHE_LOCK:
        if len(_JSON_CACHE) >= _JSON_CACHE_MAX:
            for stale in sorted(_JSON_CACHE, key=lambda key: _JSON_CACHE[key][0])[: _JSON_CACHE_MAX // 4]:
                _JSON_CACHE.pop(stale, None)
        _JSON_CACHE[url] = (now, data)
    return data


def _search_deezer(query: str, kind: str, limit: int) -> list[dict]:
    endpoint = {"Artists": "artist", "Albums": "album", "Playlists": "playlist"}.get(kind, "track")
    data = _get_json("https://api.deezer.com/search/" + endpoint + "?" + urlencode({"q": query, "limit": limit}))
    results: list[dict] = []
    for row in data.get("data", []):
        if endpoint == "artist":
            title = row.get("name") or "Unknown artist"
            results.append({"kind": "Artists", "provider": "Deezer", "title": title, "artist": title,
                "album": f'{row.get("nb_album", 0)} albums', "duration": None,
                "cover": row.get("picture_medium") or row.get("picture") or "", "url": row.get("link") or "",
                "preview": "", "query": title})
        elif endpoint == "album":
            artist = (row.get("artist") or {}).get("name") or "Unknown artist"
            title = row.get("title") or "Unknown album"
            results.append({"kind": "Albums", "provider": "Deezer", "title": title, "artist": artist,
                "album": f'{row.get("nb_tracks", 0)} tracks', "duration": None,
                "cover": row.get("cover_medium") or row.get("cover") or "", "url": row.get("link") or "",
                "preview": "", "query": f"{artist} - {title}"})
        elif endpoint == "playlist":
            owner = (row.get("user") or {}).get("name") or "Unknown creator"
            title = row.get("title") or "Untitled playlist"
            results.append({"kind": "Playlists", "provider": "Deezer", "title": title, "artist": owner,
                "album": f'{row.get("nb_tracks", 0)} tracks', "duration": None,
                "cover": row.get("picture_medium") or row.get("picture") or "", "url": row.get("link") or "",
                "preview": "", "query": title})
        else:
            artist = row.get("artist") or {}
            album = row.get("album") or {}
            results.append({"kind": "Tracks", "provider": "Deezer", "title": row.get("title") or "Unknown title",
                "artist": artist.get("name") or "Unknown artist", "album": album.get("title") or "",
                "duration": row.get("duration"), "cover": album.get("cover_medium") or album.get("cover") or "",
                "url": row.get("link") or "", "preview": row.get("preview") or "",
                "query": f"{artist.get('name', '')} - {row.get('title', '')}".strip(" -")})
    return results


def _search_apple(query: str, limit: int) -> list[dict]:
    data = _get_json("https://itunes.apple.com/search?" + urlencode({"term": query, "entity": "song", "limit": limit}))
    return [{"kind": "Tracks", "provider": "Apple Music", "title": row.get("trackName") or "Unknown title",
             "artist": row.get("artistName") or "Unknown artist", "album": row.get("collectionName") or "",
             "duration": int(row["trackTimeMillis"] / 1000) if row.get("trackTimeMillis") else None,
             "cover": row.get("artworkUrl100") or "", "url": row.get("trackViewUrl") or "",
             "preview": row.get("previewUrl") or "",
             "query": f"{row.get('artistName', '')} - {row.get('trackName', '')}".strip(" -")}
            for row in data.get("results", [])]


def _search_ytdlp(source: str, prefix: str, query: str, limit: int) -> list[dict]:
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required for YouTube and SoundCloud search.") from exc
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist",
            "ignoreerrors": True, "socket_timeout": 12}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"{prefix}{min(limit, 20)}:{query}", download=False)
    results = []
    for row in (info or {}).get("entries") or []:
        if not row:
            continue
        uploader = row.get("uploader") or row.get("channel") or "Unknown artist"
        title = row.get("title") or "Unknown title"
        results.append({"kind": "Tracks", "provider": source, "title": title, "artist": uploader, "album": "",
            "duration": row.get("duration"), "cover": row.get("thumbnail") or "",
            "url": row.get("webpage_url") or row.get("url") or "", "preview": "",
            "query": f"{uploader} - {title}".strip(" -")})
    return results


def search_catalog(query: str, provider: str = "All", limit: int = 20, kind: str = "All", sort: bool = True) -> list[dict]:
    """Search public music catalogs. Artist/album/playlist discovery is provided by Deezer.

    Providers are queried concurrently (they used to run one after another, so
    a "All catalogs" search cost the *sum* of four network round-trips instead
    of the slowest one). Result order stays deterministic: provider order.
    """
    query = query.strip()
    if not query:
        return []
    kind = kind if kind in {"All", "Tracks", "Artists", "Albums", "Playlists"} else "All"
    providers = ["Deezer", "Apple Music", "YouTube", "SoundCloud"] if provider in {"All", "All catalogs"} else [provider]
    if kind in {"Artists", "Albums", "Playlists"}:
        # These catalog object types are supported by Deezer's public search endpoints.
        providers = ["Deezer"]
    jobs = []
    if "Deezer" in providers:
        jobs.append(("Deezer", lambda: _search_deezer(query, kind, limit)))
    if kind in {"All", "Tracks"}:
        if "Apple Music" in providers:
            jobs.append(("Apple Music", lambda: _search_apple(query, limit)))
        for source, prefix in (("YouTube", "ytsearch"), ("SoundCloud", "scsearch")):
            if source in providers:
                jobs.append((source, lambda source=source, prefix=prefix: _search_ytdlp(source, prefix, query, limit)))
    results: list[dict] = []
    errors: list[str] = []
    if jobs:
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [(label, pool.submit(fn)) for label, fn in jobs]
            for label, future in futures:
                try:
                    results.extend(future.result())
                except Exception as exc:
                    errors.append(f"{label}: {exc}")
    if not results and errors:
        raise RuntimeError("Music search providers were unavailable. " + " | ".join(errors[:3]))
    if sort:
        results.sort(key=lambda row: (row.get("title", "").casefold(), row.get("artist", "").casefold()))
    return results[:limit]


def _lyrics_json(url: str, timeout: int = 16) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": "UniversalMediaStudio/1.0 (lyrics lookup)",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _plain_lyric_lines(text: str) -> list[dict]:
    return [
        {"time_ms": -1, "text": line.strip()}
        for line in str(text or "").splitlines()
        if line.strip()
    ]


def _timed_rows(rows) -> list[dict]:
    result = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        raw_time = row.get("start", row.get("time_ms"))
        try:
            time_ms = int(float(raw_time))
        except (TypeError, ValueError):
            continue
        if text and time_ms >= 0:
            result.append({"time_ms": time_ms, "text": text})
    result.sort(key=lambda item: item["time_ms"])
    return result


def _lyrics_candidate(
    source: str,
    title: str,
    artist: str,
    duration: float | None,
    lines: list[dict],
    plain: str = "",
    sync_level: str = "plain",
    match_title: str = "",
    match_artist: str = "",
    match_duration: float | None = None,
    preferred: bool = False,
) -> dict | None:
    lines = [dict(row) for row in (lines or []) if str(row.get("text") or "").strip()]
    if not lines and plain:
        lines = _plain_lyric_lines(plain)
    if not lines:
        return None
    score = lyric_match_score(
        title,
        artist,
        match_title or title,
        match_artist or artist,
        duration,
        match_duration,
    )
    if score < 0.62:
        return None
    timed = any(int(row.get("time_ms", -1)) >= 0 for row in lines)
    level = str(sync_level or ("line" if timed else "plain")).lower()
    quality = 4 if any(value in level for value in ("syllable", "word", "character")) else (3 if timed else 0)
    return {
        "source": source,
        "title": match_title or title,
        "artist": match_artist or artist,
        "duration": match_duration,
        "lines": lines,
        "synchronized": timed,
        "sync_level": level,
        "quality": quality,
        "match_score": score,
        "preferred": bool(preferred),
    }


def _fetch_lrclib_lyrics(title: str, artist: str, duration: float | None) -> list[dict]:
    params = urlencode({"track_name": title, "artist_name": artist})
    request = Request(
        "https://lrclib.net/api/search?" + params,
        headers={"User-Agent": "UniversalMediaStudio/1.0 (lyrics lookup)", "Accept": "application/json"},
    )
    with urlopen(request, timeout=16) as response:
        rows = json.loads(response.read().decode("utf-8"))
    candidates = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        synced = str(row.get("syncedLyrics") or "")
        plain = str(row.get("plainLyrics") or "")
        lines = parse_lrc(synced)
        candidate = _lyrics_candidate(
            "LRCLIB",
            title,
            artist,
            duration,
            lines,
            plain,
            "line" if lines else "plain",
            row.get("trackName") or "",
            row.get("artistName") or "",
            row.get("duration"),
        )
        if candidate:
            candidates.append(candidate)
    return candidates


def _fetch_liriqo_lyrics(
    title: str, artist: str, album: str, duration: float | None
) -> list[dict]:
    params = {"title": title, "artist": artist, "full": "1"}
    if album:
        params["album"] = album
    if duration and duration > 0:
        params["duration"] = str(int(duration))
    url = "https://api.liriqo-alfarrizi.my.id/v1/lyrics?" + urlencode(params)
    data = _lyrics_json(url, timeout=24)
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    tracks = data.get("tracks") if isinstance(data.get("tracks"), list) else []
    primary = data.get("primary")
    if isinstance(primary, dict):
        tracks = [primary] + tracks

    candidates = []
    seen = set()
    for track in tracks:
        if not isinstance(track, dict):
            continue
        track_title = str(track.get("title") or metadata.get("title") or title)
        track_artist = str(track.get("artist") or metadata.get("artist") or artist)
        track_duration = track.get("duration") or metadata.get("duration")
        timed = _timed_rows(track.get("timed"))
        if not timed and track.get("lrc"):
            timed = parse_lrc(str(track.get("lrc")))
        plain = str(track.get("plain") or "")
        source = str(
            track.get("upstreamProvider")
            or track.get("lyricsSource")
            or track.get("provider")
            or "LiriQo"
        )
        sync_level = str(track.get("syncLevel") or ("line" if timed else "plain"))
        key = (source, tuple((line["time_ms"], line["text"]) for line in timed[:4]), plain[:80])
        if key in seen:
            continue
        seen.add(key)
        candidate = _lyrics_candidate(
            source,
            title,
            artist,
            duration,
            timed,
            plain,
            sync_level,
            track_title,
            track_artist,
            track_duration,
            preferred=track is primary,
        )
        if candidate:
            candidates.append(candidate)
    return candidates


def _fetch_betterlyrics_lyrics(
    endpoint: str,
    source: str,
    title: str,
    artist: str,
    album: str,
    duration: float | None,
) -> list[dict]:
    params = {"s": title, "a": artist, "al": album, "d": str(int(duration or 0))}
    url = "https://api.betterlyrics.org/" + endpoint.lstrip("/") + "?" + urlencode(params)
    data = _lyrics_json(url, timeout=14)
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    raw = str(data.get("ttml") or data.get("lyrics") or "")
    lines = parse_ttml(raw) if endpoint == "getLyrics" else parse_lrc(raw)
    return [
        candidate
        for candidate in [
            _lyrics_candidate(
                source,
                title,
                artist,
                duration,
                lines,
                "",
                "syllable" if endpoint == "getLyrics" else "line",
            )
        ]
        if candidate
    ]


class LyricsSearchWorker(QThread):
    # Keep completed as plain text for the legacy Widgets UI. The QML player
    # consumes structuredCompleted so it can synchronize timestamped rows.
    completed = Signal(str)
    structuredCompleted = Signal(str)
    failed = Signal(str)

    def __init__(self, title: str, artist: str, parent=None, album: str = "", duration: float | None = None):
        super().__init__(parent)
        self.title = str(title or "").strip()
        self.artist = str(artist or "").strip()
        self.album = str(album or "").strip()
        try:
            self.duration = float(duration or 0) or None
        except (TypeError, ValueError):
            self.duration = None

    def run(self):
        providers = [
            ("LRCLIB", lambda: _fetch_lrclib_lyrics(self.title, self.artist, self.duration)),
            ("LiriQo", lambda: _fetch_liriqo_lyrics(self.title, self.artist, self.album, self.duration)),
            ("Better Lyrics · TTML", lambda: _fetch_betterlyrics_lyrics(
                "getLyrics", "Better Lyrics · TTML", self.title, self.artist, self.album, self.duration
            )),
            ("Better Lyrics · KuGou", lambda: _fetch_betterlyrics_lyrics(
                "kugou/getLyrics", "Better Lyrics · KuGou", self.title, self.artist, self.album, self.duration
            )),
        ]
        candidates = []
        errors = []
        try:
            # Provider calls are independent; fan them out so a slow endpoint
            # does not add its full timeout after every other source.
            with ThreadPoolExecutor(max_workers=len(providers)) as pool:
                futures = [(name, pool.submit(fetch)) for name, fetch in providers]
                for name, future in futures:
                    try:
                        candidates.extend(future.result())
                    except Exception as exc:
                        errors.append(f"{name}: {exc}")

            synced = [item for item in candidates if item["synchronized"]]
            plain = [item for item in candidates if not item["synchronized"]]
            best_synced = max(
                synced,
                key=lambda item: (item["match_score"], item["quality"], item["preferred"]),
                default=None,
            )
            best_plain = max(
                plain,
                key=lambda item: (item["match_score"], item["preferred"]),
                default=None,
            )
            # Do not sacrifice a clearly better recording match just to get
            # timestamps. Prefer sync when its metadata match is comparable.
            if best_synced and (
                best_plain is None
                or best_synced["match_score"] >= best_plain["match_score"] - 0.10
            ):
                selected = best_synced
            else:
                selected = best_plain
            if selected is None:
                unavailable = len(errors) == len(providers)
                message = (
                    "Lyrics providers are temporarily unavailable. Try again later."
                    if unavailable
                    else "No lyrics found for this track."
                )
                payload = {
                    "title": self.title,
                    "artist": self.artist,
                    "request_title": self.title,
                    "request_artist": self.artist,
                    "synchronized": False,
                    "source": "",
                    "sync_level": "plain",
                    "lines": [],
                    "message": message,
                    "providers_checked": [name for name, _fetch in providers],
                }
            else:
                payload = {
                    "title": selected["title"],
                    "artist": selected["artist"],
                    "request_title": self.title,
                    "request_artist": self.artist,
                    "duration": selected.get("duration"),
                    "synchronized": selected["synchronized"],
                    "source": selected["source"],
                    "sync_level": selected["sync_level"],
                    "lines": selected["lines"],
                    "message": "" if selected["synchronized"] else "These lyrics are not timestamped.",
                    "providers_checked": [name for name, _fetch in providers],
                }
            display_text = "\n".join(line["text"] for line in payload["lines"])
            if not display_text:
                display_text = payload["message"] or "No lyrics found for this track."
            self.completed.emit(display_text)
            self.structuredCompleted.emit(json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            self.failed.emit(f"Lyrics lookup failed: {exc}")

class CatalogSearchWorker(QThread):
    completed = Signal(object)
    progress = Signal(object)
    failed = Signal(str)

    def __init__(self, query: str, provider: str = "All", kind: str = "All", parent=None):
        super().__init__(parent)
        self.query = query
        self.provider = provider
        self.kind = kind

    def run(self):
        try:
            if self.kind != "All":
                self.completed.emit(search_catalog(self.query, self.provider, kind=self.kind))
                return
            stages = [("Tracks", 60)]
            if self.provider in {"All", "All catalogs", "Deezer"}:
                stages += [("Artists", 30), ("Albums", 30), ("Playlists", 30)]
            by_stage: dict[int, list[dict]] = {}
            errors: list[str] = []
            # Stages are independent HTTP calls: fetch them in parallel, but show
            # rows in stage order (Tracks, Artists, Albums, Playlists) as they arrive.
            with ThreadPoolExecutor(max_workers=len(stages)) as pool:
                futures = {
                    pool.submit(search_catalog, self.query, self.provider, limit=limit, kind=kind, sort=False): index
                    for index, (kind, limit) in enumerate(stages)
                }
                for future in as_completed(futures):
                    try:
                        by_stage[futures[future]] = future.result()
                        self.progress.emit([row for key in sorted(by_stage) for row in by_stage[key]])
                    except Exception as exc:
                        errors.append(str(exc))
            rows = [row for key in sorted(by_stage) for row in by_stage[key]]
            if not rows and errors:
                raise RuntimeError(errors[0])
            self.completed.emit(rows)
        except Exception as exc:
            self.failed.emit(f"Music search failed: {exc}")


def _deezer_track_row(row: dict, cover: str = "", album: str = "") -> dict:
    artist = (row.get("artist") or {}).get("name") or ""
    alb = row.get("album") or {}
    title = row.get("title") or "Unknown title"
    return {"kind": "Tracks", "provider": "Deezer", "title": title, "artist": artist or "Unknown artist",
            "album": alb.get("title") or album, "duration": row.get("duration"),
            "cover": alb.get("cover_medium") or alb.get("cover") or cover,
            "url": row.get("link") or "", "preview": row.get("preview") or "",
            "query": f"{artist} - {title}".strip(" -")}


def load_collection(kind: str, url: str) -> dict:
    """Load the track list of a Deezer album, playlist or artist."""
    match = re.search(r"deezer\.com/(?:[a-z]{2}/)?(album|artist|playlist)/(\d+)", url or "")
    if not match:
        raise RuntimeError("This item cannot be opened inside the app.")
    obj, oid = match.groups()
    base = "https://api.deezer.com/"
    if obj == "album":
        data = _get_json(f"{base}album/{oid}")
        cover = data.get("cover_xl") or data.get("cover_big") or data.get("cover_medium") or ""
        rows = ((data.get("tracks") or {}).get("data")) or []
        tracks = [_deezer_track_row(r, cover, data.get("title") or "") for r in rows]
        for t in tracks:
            if not t["artist"] or t["artist"] == "Unknown artist":
                t["artist"] = (data.get("artist") or {}).get("name") or "Unknown artist"
        return {"kind": "Albums", "title": data.get("title") or "Album",
                "subtitle": (data.get("artist") or {}).get("name") or "", "cover": cover, "url": url, "tracks": tracks}
    if obj == "playlist":
        data = _get_json(f"{base}playlist/{oid}")
        cover = data.get("picture_xl") or data.get("picture_big") or data.get("picture_medium") or ""
        rows = _get_json(f"{base}playlist/{oid}/tracks?limit=300").get("data") or []
        tracks = [_deezer_track_row(r, cover) for r in rows]
        return {"kind": "Playlists", "title": data.get("title") or "Playlist",
                "subtitle": (data.get("user") or {}).get("name") or "", "cover": cover, "url": url, "tracks": tracks}
    data = _get_json(f"{base}artist/{oid}")
    cover = data.get("picture_xl") or data.get("picture_big") or data.get("picture_medium") or ""
    rows = _get_json(f"{base}artist/{oid}/top?limit=50").get("data") or []
    tracks = [_deezer_track_row(r, cover) for r in rows]
    return {"kind": "Artists", "title": data.get("name") or "Artist",
            "subtitle": f'{data.get("nb_album", 0)} albums', "cover": cover, "url": url, "tracks": tracks}


class CollectionWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, kind: str, url: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.url = url

    def run(self):
        try:
            self.completed.emit(load_collection(self.kind, self.url))
        except Exception as exc:
            self.failed.emit(f"Could not open this item: {exc}")



SPOTIFY_URL_RE = re.compile(
    r"(?:https?://)?open\.spotify\.com/(?:intl-[a-z]{2}(?:-[A-Z]{2})?/)?(track|album|playlist)/([A-Za-z0-9]+)",
    re.IGNORECASE,
)
SPOTIFY_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)



_SPOTIFY_PLAYLIST_QUERY_HASH = "86dde7b9d9356e2369414647cf6950cfed96e778e129cfdfc99aea6c1613b3b0"


def _spotify_anonymous_token() -> str:
    for url in (
        "https://open.spotify.com/embed/api/token",
        "https://open.spotify.com/get_access_token?reason=transport&productType=web_player",
    ):
        try:
            request = Request(url, headers={"User-Agent": SPOTIFY_USER_AGENT, "Accept": "application/json"})
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("accessToken"):
                return payload["accessToken"]
        except Exception:
            continue
    raise RuntimeError("Spotify did not issue an anonymous embed token.")


def _spotify_playlist_tail(spotify_id: str, token: str, offset: int) -> list[dict]:
    rows = []
    while True:
        params = urlencode({
            "operationName": "fetchPlaylistContents",
            "variables": json.dumps({
                "uri": f"spotify:playlist:{spotify_id}", "offset": offset, "limit": 100,
                "enableWatchFeedEntrypoint": False, "includeEpisodeContentRatingsV2": False,
            }),
            "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": _SPOTIFY_PLAYLIST_QUERY_HASH}}),
        })
        request = Request(
            "https://api-partner.spotify.com/pathfinder/v1/query?" + params,
            headers={"User-Agent": SPOTIFY_USER_AGENT, "Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("errors"):
            raise RuntimeError("Spotify rejected the anonymous playlist query.")
        content = payload["data"]["playlistV2"]["content"]
        batch = content.get("items") or []
        rows.extend(batch)
        total = int(content.get("totalCount") or 0)
        offset += len(batch)
        if not batch or offset >= total:
            break
    return rows


def resolve_spotify_link(url: str) -> dict:
    """Resolve public Spotify track/album/playlist metadata from the embed page.

    This deliberately uses Spotify's public embed metadata, not the Spotify Web
    API, so it does not require a client ID, client secret, or user token.
    Spotify's embed currently exposes up to 100 playlist rows.
    """
    match = SPOTIFY_URL_RE.search(url.strip())
    if not match:
        raise ValueError("Paste a valid public Spotify track, album, or playlist URL.")
    kind, spotify_id = match.group(1).lower(), match.group(2)
    request = Request(
        f"https://open.spotify.com/embed/{kind}/{spotify_id}",
        headers={"User-Agent": SPOTIFY_USER_AGENT, "Accept": "text/html"},
    )
    try:
        with urlopen(request, timeout=18) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(f"Could not reach Spotify's public embed page: {exc}") from exc
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.+?)</script>',
        html, re.DOTALL,
    )
    if not match:
        raise RuntimeError("Spotify did not return readable embed metadata. The playlist may be private or Spotify may have changed its page.")
    try:
        entity = json.loads(match.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError("Spotify's embed metadata format has changed; try again later.") from exc
    name = entity.get("name") or entity.get("title") or "Spotify collection"
    cover_sources = ((entity.get("coverArt") or {}).get("sources") or
                     (entity.get("visualIdentity") or {}).get("image") or [])
    cover = max(cover_sources, key=lambda row: row.get("width", row.get("maxWidth", 0)) or 0).get("url") if cover_sources else ""
    tracks = []
    if kind == "track":
        artists = [row.get("name", "") for row in entity.get("artists") or [] if row.get("name")]
        tracks.append({"title": name, "artist": ", ".join(artists) or "Unknown artist",
                       "album": (entity.get("albumOfTrack") or {}).get("name", ""),
                       "query": f"{', '.join(artists)} - {name}".strip(" -"), "cover": cover})
    else:
        owner = entity.get("subtitle") or ""
        for position, item in enumerate(entity.get("trackList") or [], start=1):
            title = (item.get("title") or "").strip()
            artists = [name.strip() for name in (item.get("subtitle") or owner).split(",") if name.strip()]
            if not title or title.lower() in {"unavailable track", "track unavailable"}:
                continue
            artist = ", ".join(artists) or "Unknown artist"
            tracks.append({"title": title, "artist": artist, "album": name if kind == "album" else "",
                           "query": f"{artist} - {title}", "cover": cover, "position": position})
    limited = False
    if kind == "playlist" and len(tracks) >= 100:
        # Best-effort extension using the anonymous token public Spotify embeds
        # mint for their own player. This is not a Spotify Web API client token.
        try:
            token = _spotify_anonymous_token()
            extra = _spotify_playlist_tail(spotify_id, token, len(tracks))
            for position, item in enumerate(extra, start=len(tracks) + 1):
                wrapper = item.get("itemV2") or {}
                if wrapper.get("__typename") != "TrackResponseWrapper":
                    continue
                data = wrapper.get("data") or {}
                title = (data.get("name") or "").strip()
                album = data.get("albumOfTrack") or {}
                artists = [((artist.get("profile") or {}).get("name") or "").strip()
                           for artist in ((data.get("artists") or {}).get("items") or [])]
                artists = [artist for artist in artists if artist]
                if not title:
                    continue
                artist = ", ".join(artists) or "Unknown artist"
                tracks.append({"title": title, "artist": artist, "album": album.get("name", ""),
                               "query": f"{artist} - {title}", "cover": cover, "position": position})
        except Exception:
            # A stale undocumented Spotify query should not break a playlist
            # that already resolved through the stable public embed page.
            limited = True
    if not tracks:
        raise RuntimeError("No playable tracks were exposed by this Spotify link. Check that the collection is public.")
    return {"kind": kind, "name": name, "owner": entity.get("subtitle") or "",
            "cover": cover, "tracks": tracks, "limited": limited}


class SpotifyResolveWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.completed.emit(resolve_spotify_link(self.url))
        except Exception as exc:
            self.failed.emit(str(exc))


@lru_cache(maxsize=4096)
def _match_text(value: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"\b(feat|ft|featuring)\b.*$", "", value, flags=re.IGNORECASE)
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _music_match_score(entry: dict, metadata: dict | None, query: str) -> float:
    from difflib import SequenceMatcher
    metadata = metadata or {}
    expected_title = _match_text(metadata.get("title") or query)
    expected_artist = _match_text(metadata.get("artist") or "")
    actual_title = _match_text(entry.get("title") or "")
    actual_artist = _match_text(entry.get("artist") or entry.get("uploader") or entry.get("channel") or "")
    title_score = SequenceMatcher(None, expected_title, actual_title).ratio() if expected_title and actual_title else 0.0
    artist_score = SequenceMatcher(None, expected_artist, actual_artist).ratio() if expected_artist and actual_artist else 0.5
    return title_score * 0.78 + artist_score * 0.22


def run_music_download(query: str, output_dir: str, cancel_event=None,
                        progress_cb=None, log_cb=None, ffmpeg_path=None, metadata=None, settings=None) -> list[str]:
    """Find a matching public audio source with yt-dlp and tag an MP3 locally.

    Spotify is used only for public track metadata. This path never calls
    Spotify's authenticated Web API and does not invoke spotDL.
    """
    query = str(query or "").strip()
    if not query:
        raise ValueError("The music search query is empty.")
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required. Install the main application requirements.") from exc

    output = Path(output_dir).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    started_ns = time.time_ns()
    last_report = {"pct": -1, "t": 0.0}

    # Prefer one authoritative cover source. Download catalog artwork once and
    # let Mutagen embed it, instead of asking yt-dlp to embed its thumbnail too.
    # Running both post-processors used to leave multiple APIC frames in MP3s.
    image_data = b""
    mime = "image/jpeg"
    if metadata and metadata.get("cover"):
        try:
            request = Request(str(metadata["cover"]), headers={"User-Agent": SPOTIFY_USER_AGENT})
            with urlopen(request, timeout=12) as response:
                image_data = response.read()
            if image_data.startswith(b"\x89PNG"):
                mime = "image/png"
            elif image_data.startswith(b"\xff\xd8"):
                mime = "image/jpeg"
            else:
                image_data = b""
                if log_cb:
                    log_cb("Catalog artwork had an unsupported image format; using the source thumbnail instead.")
        except Exception as art_error:
            image_data = b""
            if log_cb:
                log_cb(f"Catalog artwork could not be downloaded; using the source thumbnail instead: {art_error}")

    def report(data):
        if cancel_event and cancel_event.is_set():
            raise CancelledError("Music download cancelled.")
        status = data.get("status")
        if status == "downloading" and progress_cb:
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            percent = int(downloaded * 95 / total) if total else 0
            speed = data.get("speed")
            eta = data.get("eta")
            detail = "Downloading matched audio"
            if speed:
                detail += f" · {speed / 1024 / 1024:.1f} MB/s"
            if eta is not None:
                detail += f" · {eta}s left"
            percent = max(0, min(95, percent))
            now = time.monotonic()
            if percent != last_report["pct"] or now - last_report["t"] >= 1.0:  # throttle hook spam
                last_report.update(pct=percent, t=now)
                progress_cb(percent, detail)
        elif status == "finished" and progress_cb:
            progress_cb(96, "Download complete · tagging audio…")

    postprocessors = [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"},
        {"key": "FFmpegMetadata", "add_metadata": True},
    ]
    # If catalog artwork was fetched, Mutagen embeds exactly that one image.
    # Otherwise retain yt-dlp's thumbnail embed as a useful fallback.
    if not image_data:
        postprocessors.append({"key": "EmbedThumbnail"})

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(output / "%(title).180B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "socket_timeout": 25,
        "retries": 3,
        "fragment_retries": 3,
        "continuedl": True,
        "overwrites": False,
        "writethumbnail": not bool(image_data),
        "progress_hooks": [report],
        "postprocessors": postprocessors,
    }
    if ffmpeg_path:
        options["ffmpeg_location"] = str(ffmpeg_path)
    net_options = network_options(settings)
    options.update(net_options)
    if log_cb:
        log_cb("Searching YouTube for the closest audio match using yt-dlp (no Spotify API credentials).")
        log_cb(f"Search: {query}")
    if progress_cb:
        progress_cb(1, "Finding a matching audio source…")
    downloaded: list[str] = []
    try:
        # Ranking only needs title/uploader/duration, so search with flat extraction:
        # one request instead of fully resolving all five candidate videos.
        search_opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist",
                       "ignoreerrors": False, "socket_timeout": 25, **net_options}
        with yt_dlp.YoutubeDL(search_opts) as search_ydl:
            search = search_ydl.extract_info(f"ytsearch5:{query}", download=False)
        entries = [entry for entry in (search or {}).get("entries") or [] if entry]
        if not entries:
            raise RuntimeError("YouTube search returned no matching tracks.")
        score, selected = max(((_music_match_score(entry, metadata, query), entry) for entry in entries),
                              key=lambda pair: pair[0])
        selected_url = selected.get("webpage_url") or selected.get("original_url") or selected.get("url")
        if selected_url and not str(selected_url).startswith(("http://", "https://")):
            selected_url = "https://www.youtube.com/watch?v=" + str(selected_url)
        if not selected_url:
            raise RuntimeError("The best matching search result did not include a playable media URL.")
        if log_cb:
            log_cb(f"Best match: {selected.get('title', 'Unknown title')} — {selected.get('uploader') or selected.get('channel') or selected.get('artist') or 'Unknown artist'} (match {score:.0%})")
            if score < 0.38:
                log_cb("Warning: this is a weak metadata match. Check the downloaded track before keeping it.")
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(selected_url, download=True)
        for item in (info or {}).get("requested_downloads") or []:
            filepath = item.get("filepath") or item.get("_filename")
            if filepath and Path(filepath).suffix.lower() in AUDIO_EXTENSIONS and Path(filepath).is_file():
                downloaded.append(str(filepath))
    except Exception as exc:
        if cancel_event and cancel_event.is_set():
            raise CancelledError("Music download cancelled.") from exc
        message = str(exc)
        if "ffmpeg" in message.lower() or "postprocessor" in message.lower():
            raise RuntimeError("Audio was found, but FFmpeg could not convert/tag it. Install FFmpeg and make sure ffmpeg and ffprobe are on PATH.") from exc
        raise RuntimeError(f"Could not download a matching audio source: {message}") from exc
    if cancel_event and cancel_event.is_set():
        raise CancelledError("Music download cancelled.")
    # yt-dlp reports the exact final paths. Only if it did not, fall back to
    # files modified since the job started (replaces two full library scans
    # that ran before *and* after every single track download).
    files = sorted(set(downloaded))
    if not files:
        files = sorted(str(p) for p in output.rglob("*")
                       if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS and p.stat().st_mtime_ns >= started_ns - 2_000_000_000)
    if not files:
        raise RuntimeError("yt-dlp completed without producing an audio file. Check FFmpeg and the selected source.")
    # Normalize ID3 metadata on every generated MP3, even when no catalog
    # metadata was supplied. Some sources already contain cover art and yt-dlp
    # may add a thumbnail too; retain one front-cover APIC frame at most.
    try:
        from mutagen.id3 import ID3, APIC, TALB, TIT2, TPE1
        tag_data = metadata or {}
        title = str(tag_data.get("title") or "")
        artist = str(tag_data.get("artist") or "")
        album = str(tag_data.get("album") or "")
        deduplicated = 0
        for file_path in files:
            try:
                tags = ID3(file_path)
            except Exception:
                tags = ID3()
            changed = False
            if title:
                tags.setall("TIT2", [TIT2(encoding=3, text=title)])
                changed = True
            if artist:
                tags.setall("TPE1", [TPE1(encoding=3, text=artist)])
                changed = True
            if album:
                tags.setall("TALB", [TALB(encoding=3, text=album)])
                changed = True

            pictures = tags.getall("APIC")
            if image_data:
                # Catalog art is authoritative: replace all inherited pictures.
                tags.delall("APIC")
                tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=image_data))
                changed = True
            elif len(pictures) > 1:
                # Otherwise preserve the existing front cover (or first image)
                # and discard duplicate attached pictures.
                keep = next((picture for picture in pictures if picture.type == 3), pictures[0])
                tags.delall("APIC")
                tags.add(keep)
                changed = True
                deduplicated += len(pictures) - 1
            if changed:
                tags.save(file_path)
        if deduplicated and log_cb:
            log_cb(f"Removed {deduplicated} duplicate embedded cover image(s).")
    except Exception as tag_error:
        if log_cb:
            log_cb(f"Audio tags could not be normalized; keeping the downloaded MP3: {tag_error}")
    if log_cb:
        log_cb("Saved tagged audio: " + ", ".join(Path(path).name for path in files))
    if progress_cb:
        progress_cb(100, "Music download complete")
    return files


def _audio_metadata(path: Path) -> dict:
    data = {"title": path.stem, "artist": "Unknown artist", "album": "", "duration": None, "cover": ""}
    try:
        from mutagen import File as MutagenFile
        media = MutagenFile(str(path), easy=True)
        if media:
            tags = media.tags or {}
            for key, field in (("title", "title"), ("artist", "artist"), ("album", "album")):
                value = tags.get(key)
                if value:
                    data[field] = str(value[0] if isinstance(value, (list, tuple)) else value)
            info = getattr(media, "info", None)
            length = getattr(info, "length", None)
            if length:
                data["duration"] = int(length)
        raw = MutagenFile(str(path), easy=False)
        pictures = []
        tags = getattr(raw, "tags", None)
        if tags:
            for key in tags.keys():
                if str(key).startswith("APIC"):
                    pictures.append(getattr(tags[key], "data", b""))
            for key in ("covr",):
                try:
                    pictures.extend(bytes(item) for item in tags.get(key, []))
                except Exception:
                    pass
        pictures.extend(getattr(raw, "pictures", []) or [])
        if pictures:
            first = pictures[0]
            image_bytes = getattr(first, "data", first)
            if image_bytes:
                artwork_dir = APP_DIR / "artwork"
                artwork_dir.mkdir(parents=True, exist_ok=True)
                # Content-addressed: tracks of one album share a single cover file.
                digest = hashlib.sha1(bytes(image_bytes)).hexdigest()
                image_path = artwork_dir / f"{digest}.jpg"
                if not image_path.exists():
                    image_path.write_bytes(bytes(image_bytes))
                data["cover"] = image_path.as_uri()
    except Exception:
        pass
    return data


LIBRARY_CACHE_FILE = APP_DIR / "library_cache.json"
_LIBRARY_CACHE_VERSION = 2


def _load_library_cache() -> dict:
    try:
        data = json.loads(LIBRARY_CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("version") == _LIBRARY_CACHE_VERSION:
            return data.get("files") or {}
    except (OSError, ValueError):
        pass
    return {}


def _cover_missing(cover: str) -> bool:
    if not cover:
        return False
    try:
        return not os.path.exists(url2pathname(urlparse(cover).path))
    except Exception:
        return True


def scan_audio_library(folder: str | Path) -> list[dict]:
    """List audio files with tags.

    Tag/artwork parsing (two mutagen opens + image hashing per file) dominated
    refresh time, and ran on every refresh for every file. Parsed rows are now
    cached on disk keyed by (path, mtime, size), so only new/changed files are
    parsed and an unchanged library scans at os.stat speed.
    """
    root = Path(folder).expanduser()
    if not root.exists():
        return []
    root_prefix = str(root) + os.sep
    old_cache = _load_library_cache()
    new_cache = {key: value for key, value in old_cache.items() if not key.startswith(root_prefix)}
    dirty = False
    files = []
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            if os.path.splitext(name)[1].lower() not in AUDIO_EXTENSIONS:
                continue
            full = os.path.join(dirpath, name)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            cached = old_cache.get(full)
            if (cached and cached.get("mtime_ns") == stat.st_mtime_ns and cached.get("size") == stat.st_size
                    and not _cover_missing(cached["row"].get("cover", ""))):
                row = dict(cached["row"])
            else:
                row = _audio_metadata(Path(full))
                dirty = True
            new_cache[full] = {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size, "row": dict(row)}
            row["path"] = full
            row["modified"] = stat.st_mtime
            files.append(row)
    if dirty or len(new_cache) != len(old_cache):
        try:
            atomic_write_text(LIBRARY_CACHE_FILE, json.dumps({"version": _LIBRARY_CACHE_VERSION, "files": new_cache}, ensure_ascii=False))
        except OSError:
            pass
    return sorted(files, key=lambda item: (item["modified"], item["title"].casefold()), reverse=True)


def load_music_playlists() -> dict[str, list[str]]:
    data = load_settings().get(PLAYLISTS_KEY, {})
    if not isinstance(data, dict):
        return {}
    result = {}
    for name, paths in data.items():
        if isinstance(name, str) and isinstance(paths, list):
            result[name] = [str(path) for path in paths if isinstance(path, str)]
    return result


def save_music_playlists(playlists: dict[str, list[str]]) -> None:
    update_settings(**{PLAYLISTS_KEY: playlists})
