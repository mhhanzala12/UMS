"""Music discovery, local library helpers, and credential-free audio matching.

Inspired by Unstream's music-first workflows. This module is adapted for the
native PySide6 application and keeps media processing on the user's machine.
"""
from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PySide6.QtCore import QThread, Signal

from .config import load_settings, save_settings

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav", ".aiff", ".wma"}
MUSIC_LIBRARY_DIR = Path.home() / "Music" / "UniversalMediaStudio"
PLAYLISTS_KEY = "music_playlists"


def _get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "UniversalMediaStudio/1.0 (local desktop app)"})
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def search_catalog(query: str, provider: str = "All", limit: int = 20, kind: str = "All", sort: bool = True) -> list[dict]:
    """Search public music catalogs. Artist/album/playlist discovery is provided by Deezer."""
    query = query.strip()
    if not query:
        return []
    kind = kind if kind in {"All", "Tracks", "Artists", "Albums", "Playlists"} else "All"
    providers = ["Deezer", "Apple Music", "YouTube", "SoundCloud"] if provider in {"All", "All catalogs"} else [provider]
    if kind in {"Artists", "Albums", "Playlists"}:
        # These catalog object types are supported by Deezer's public search endpoints.
        providers = ["Deezer"]
    results: list[dict] = []
    errors = []
    if "Deezer" in providers:
        endpoint = {"Artists": "artist", "Albums": "album", "Playlists": "playlist"}.get(kind, "track")
        try:
            data = _get_json("https://api.deezer.com/search/" + endpoint + "?" + urlencode({"q": query, "limit": limit}))
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
        except Exception as exc:
            errors.append(f"Deezer: {exc}")
    if kind in {"All", "Tracks"} and "Apple Music" in providers:
        try:
            data = _get_json("https://itunes.apple.com/search?" + urlencode({"term": query, "entity": "song", "limit": limit}))
            for row in data.get("results", []):
                results.append({"kind": "Tracks", "provider": "Apple Music", "title": row.get("trackName") or "Unknown title",
                    "artist": row.get("artistName") or "Unknown artist", "album": row.get("collectionName") or "",
                    "duration": int(row["trackTimeMillis"] / 1000) if row.get("trackTimeMillis") else None,
                    "cover": row.get("artworkUrl100") or "", "url": row.get("trackViewUrl") or "",
                    "preview": row.get("previewUrl") or "",
                    "query": f"{row.get('artistName', '')} - {row.get('trackName', '')}".strip(" -")})
        except Exception as exc:
            errors.append(f"Apple Music: {exc}")
    if kind in {"All", "Tracks"} and ("YouTube" in providers or "SoundCloud" in providers):
        try:
            import yt_dlp
            for source, prefix in (("YouTube", "ytsearch"), ("SoundCloud", "scsearch")):
                if source not in providers:
                    continue
                opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist", "ignoreerrors": True, "socket_timeout": 12}
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(f"{prefix}{min(limit, 20)}:{query}", download=False)
                    for row in (info or {}).get("entries") or []:
                        if not row:
                            continue
                        uploader = row.get("uploader") or row.get("channel") or "Unknown artist"
                        title = row.get("title") or "Unknown title"
                        results.append({"kind": "Tracks", "provider": source, "title": title, "artist": uploader, "album": "",
                            "duration": row.get("duration"), "cover": row.get("thumbnail") or "",
                            "url": row.get("webpage_url") or row.get("url") or "", "preview": "",
                            "query": f"{uploader} - {title}".strip(" -")})
                except Exception as exc:
                    errors.append(f"{source}: {exc}")
        except ImportError:
            errors.append("yt-dlp is required for YouTube and SoundCloud search.")
    if not results and errors:
        raise RuntimeError("Music search providers were unavailable. " + " | ".join(errors[:3]))
    if sort:
        results.sort(key=lambda row: (row.get("title", "").casefold(), row.get("artist", "").casefold()))
    return results[:limit]


class LyricsSearchWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, title: str, artist: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.artist = artist

    def run(self):
        try:
            params = urlencode({"track_name": self.title, "artist_name": self.artist})
            request = Request("https://lrclib.net/api/search?" + params, headers={"User-Agent": "UniversalMediaStudio/1.0"})
            with urlopen(request, timeout=12) as response:
                rows = json.loads(response.read().decode("utf-8"))
            if not rows:
                self.completed.emit("No lyrics found for this track.")
                return
            row = next((item for item in rows if item.get("plainLyrics") or item.get("syncedLyrics")), rows[0])
            lyrics = row.get("plainLyrics") or row.get("syncedLyrics") or "No lyrics text was returned."
            self.completed.emit(lyrics)
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
            rows: list[dict] = []
            errors: list[str] = []
            for kind, limit in stages:
                try:
                    rows += search_catalog(self.query, self.provider, limit=limit, kind=kind, sort=False)
                    self.progress.emit(list(rows))
                except Exception as exc:
                    errors.append(str(exc))
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
    before = {str(p): p.stat().st_mtime_ns for p in output.rglob("*")
              if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS}
    def report(data):
        if cancel_event and cancel_event.is_set():
            from .engine import CancelledError
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
            progress_cb(max(0, min(95, percent)), detail)
        elif status == "finished" and progress_cb:
            progress_cb(96, "Download complete · tagging audio…")

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
        "writethumbnail": True,
        "progress_hooks": [report],
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"},
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"},
        ],
    }
    if ffmpeg_path:
        options["ffmpeg_location"] = str(ffmpeg_path)
    settings = settings or {}
    connection_mode = str(settings.get("connection_mode") or "Automatic").lower()
    if connection_mode == "direct":
        options["proxy"] = ""
    elif connection_mode == "proxy":
        proxy = str(settings.get("proxy_url") or "").strip()
        if not proxy:
            raise RuntimeError("Proxy mode is selected, but no proxy URL is configured.")
        options["proxy"] = proxy
    browser = str(settings.get("cookies_browser") or "None").strip().lower()
    profile = str(settings.get("cookies_profile") or "").strip()
    if browser in {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale"}:
        options["cookiesfrombrowser"] = (browser, profile or None)
    if log_cb:
        log_cb("Searching YouTube for the closest audio match using yt-dlp (no Spotify API credentials).")
        log_cb(f"Search: {query}")
    if progress_cb:
        progress_cb(1, "Finding a matching audio source…")
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            search = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = [entry for entry in (search or {}).get("entries") or [] if entry]
            if not entries:
                raise RuntimeError("YouTube search returned no matching tracks.")
            ranked = sorted(entries, key=lambda entry: _music_match_score(entry, metadata, query), reverse=True)
            selected = ranked[0]
            selected_url = selected.get("webpage_url") or selected.get("original_url") or selected.get("url")
            if selected_url and not str(selected_url).startswith(("http://", "https://")):
                selected_url = "https://www.youtube.com/watch?v=" + str(selected_url)
            if not selected_url:
                raise RuntimeError("The best matching search result did not include a playable media URL.")
            score = _music_match_score(selected, metadata, query)
            if log_cb:
                log_cb(f"Best match: {selected.get('title', 'Unknown title')} — {selected.get('uploader') or selected.get('artist') or 'Unknown artist'} (match {score:.0%})")
                if score < 0.38:
                    log_cb("Warning: this is a weak metadata match. Check the downloaded track before keeping it.")
            ydl.download([selected_url])
    except Exception as exc:
        from .engine import CancelledError
        if cancel_event and cancel_event.is_set():
            raise CancelledError("Music download cancelled.") from exc
        message = str(exc)
        if "ffmpeg" in message.lower() or "postprocessor" in message.lower():
            raise RuntimeError("Audio was found, but FFmpeg could not convert/tag it. Install FFmpeg and make sure ffmpeg and ffprobe are on PATH.") from exc
        raise RuntimeError(f"Could not download a matching audio source: {message}") from exc
    if cancel_event and cancel_event.is_set():
        from .engine import CancelledError
        raise CancelledError("Music download cancelled.")
    files = sorted(str(p) for p in output.rglob("*") if p.is_file()
                   and p.suffix.lower() in AUDIO_EXTENSIONS
                   and (str(p) not in before or p.stat().st_mtime_ns != before[str(p)]))
    if not files:
        raise RuntimeError("yt-dlp completed without producing an audio file. Check FFmpeg and the selected source.")
    if metadata:
        try:
            from mutagen.id3 import ID3, APIC, TALB, TIT2, TPE1, TPE2
            for file_path in files:
                try:
                    tags = ID3(file_path) if Path(file_path).exists() else ID3()
                except Exception:
                    tags = ID3()
                title = str(metadata.get("title") or "")
                artist = str(metadata.get("artist") or "")
                album = str(metadata.get("album") or "")
                if title: tags.add(TIT2(encoding=3, text=title))
                if artist: tags.add(TPE1(encoding=3, text=artist))
                if album: tags.add(TALB(encoding=3, text=album))
                if metadata.get("cover"):
                    try:
                        request = Request(str(metadata["cover"]), headers={"User-Agent": SPOTIFY_USER_AGENT})
                        with urlopen(request, timeout=12) as response:
                            image_data = response.read()
                        mime = "image/png" if image_data.startswith(b"\\x89PNG") else "image/jpeg"
                        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=image_data))
                    except Exception as art_error:
                        if log_cb: log_cb(f"Cover artwork could not be embedded: {art_error}")
                tags.save(file_path)
        except Exception as tag_error:
            if log_cb: log_cb(f"Spotify tags could not be applied; keeping yt-dlp metadata: {tag_error}")
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
                artwork_dir = Path.home() / ".universal_media_studio" / "artwork"
                artwork_dir.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha1(str(path).encode("utf-8", errors="replace") + bytes(image_bytes)).hexdigest()
                image_path = artwork_dir / f"{digest}.jpg"
                if not image_path.exists():
                    image_path.write_bytes(bytes(image_bytes))
                data["cover"] = image_path.as_uri()
    except Exception:
        pass
    return data


def scan_audio_library(folder: str | Path) -> list[dict]:
    root = Path(folder).expanduser()
    if not root.exists():
        return []
    files = []
    for path in root.rglob("*"):
        try:
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                row = _audio_metadata(path)
                row["path"] = str(path)
                row["modified"] = path.stat().st_mtime
                files.append(row)
        except OSError:
            continue
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
    settings = load_settings()
    settings[PLAYLISTS_KEY] = playlists
    save_settings(settings)
