"""Qt/QML bridge for the modern Universal Media Studio desktop interface.

The bridge delegates media work to the existing engine and workers. It never
runs downloads, conversions, catalog requests, or Spotify resolution on the
GUI thread.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from .config import LOG_BACKUP_COUNT, LOG_FILE, load_settings, save_settings
from .engine import is_http_url, tool_status
from .lyrics import find_lrc_sidecar, lyric_match_score, parse_lrc
from .music import (
    AUDIO_EXTENSIONS, CatalogSearchWorker, CollectionWorker, LyricsSearchWorker,
    SpotifyResolveWorker, PLAYLISTS_KEY, load_music_playlists, save_music_playlists,
    scan_audio_library,
)
from .presets import merged_presets
from .workers import AnalyzeWorker, FunctionWorker, MediaTaskWorker

# Only the fields the QML queue/downloads view reads. The old queueJson() also
# serialised every task's options dict and up to 80 log lines on each update.
_QUEUE_FIELDS = ("id", "kind", "name", "status", "progress", "detail", "output", "outputs",
                 "group_id", "group_name", "group_cover", "music_track", "thumbnail",
                 "uploader", "duration", "view_count", "upload_date")
QUEUE_EMIT_INTERVAL_MS = 150


def _multimedia():
    """Import QtMultimedia on first use. Creating the audio device and the FFmpeg
    media backend is one of the slower parts of start-up, and it is only needed once
    the user actually plays something."""
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    return QAudioOutput, QMediaPlayer


class AppBridge(QObject):
    queueChanged = Signal()
    logUpdated = Signal()
    statusChanged = Signal(str)
    analysisReady = Signal(str)
    analysisFailed = Signal(str)
    presetsChanged = Signal(str)
    settingsChanged = Signal(str)
    searchResults = Signal(str)
    searchFinished = Signal()
    collectionReady = Signal(str)
    lyricsReady = Signal(str)
    libraryChanged = Signal(str)
    playlistsChanged = Signal(str)
    playerChanged = Signal(str)
    conversionSourceSelected = Signal(str)
    errorRaised = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = load_settings()
        self.presets = merged_presets(self.settings.get("custom_presets", {}))
        self.tasks: list[dict] = []
        self.active_task_id = None
        self.active_worker = None
        self.analysis_worker = None
        self._last_analysis_url = ""
        self._last_analysis = {}
        self.search_worker = None
        self.spotify_worker = None
        self.lyrics_worker = None
        self._lyrics_request_token = 0
        self._lyrics_download_queue: list[dict] = []
        self._lyrics_download_worker = None
        self._lyrics_download_paths: set[str] = set()
        self.collection_worker = None
        self.library = []
        self._library_loaded = False
        self._library_scanning = False
        self._library_rescan = False
        self._library_waiters: list = []
        self._library_worker = None
        self._status_cache: str | None = None
        self._status_allowed = False  # tool probing waits until the window is up
        self._status_worker = None
        self._connection_worker = None
        self._browser_profiles_worker = None
        self._is_quitting = False
        self._startup_done = False
        self._warm_worker = None
        # Progress ticks arrive many times per second; the QML side re-parses the
        # whole queue on every queueChanged, so progress updates are coalesced.
        self._queue_timer = QTimer(self)
        self._queue_timer.setSingleShot(True)
        self._queue_timer.setInterval(QUEUE_EMIT_INTERVAL_MS)
        self._queue_timer.timeout.connect(self.queueChanged.emit)
        self.playlists = load_music_playlists()
        self.current_song = {}
        self.playback_queue: list[dict] = []
        self.playback_index = -1
        self.ordered_queue: list[dict] = []
        self.shuffle_enabled = bool(self.settings.get("player_shuffle", False))
        self.repeat_mode = int(self.settings.get("player_repeat", 0))  # 0 off, 1 all, 2 one
        # The media player is created lazily (see _ensure_player).
        self._player = None
        self._audio_output = None
        # Keep lyric highlighting responsive even on backends that emit positionChanged
        # infrequently. This polls the existing player; it never creates another session.
        self._player_position_timer = QTimer(self)
        self._player_position_timer.setInterval(100)
        self._player_position_timer.timeout.connect(self._emit_player_position)
        # Persist slider changes after the drag settles, not on every pointer move.
        self._volume_persist_timer = QTimer(self)
        self._volume_persist_timer.setSingleShot(True)
        self._volume_persist_timer.setInterval(400)
        self._volume_persist_timer.timeout.connect(self._persist_player_preferences)
        self._emit_initial()

    def _ensure_player(self):
        """Create the audio output and media player the first time they are needed."""
        if self._player is not None:
            return self._player
        QAudioOutput, QMediaPlayer = _multimedia()
        audio_output = QAudioOutput(self)
        audio_output.setVolume(max(0.0, min(1.0, float(self.settings.get("player_volume", 0.75)))))
        audio_output.setMuted(bool(self.settings.get("player_muted", False)))
        player = QMediaPlayer(self)
        player.setAudioOutput(audio_output)
        player.mediaStatusChanged.connect(self._on_media_status)
        player.positionChanged.connect(lambda value: self.playerChanged.emit(json.dumps({"position": value})))
        player.durationChanged.connect(lambda value: self.playerChanged.emit(json.dumps({"duration": value})))
        player.playbackStateChanged.connect(self._on_player_state_changed)
        self._audio_output = audio_output
        self._player = player
        return player

    @property
    def player(self):
        return self._ensure_player()

    @property
    def audio_output(self):
        self._ensure_player()
        return self._audio_output

    def _duration_ms(self) -> int:
        return self._player.duration() if self._player is not None else 0

    @Slot()
    def finishStartup(self):
        """Run non-essential work once the window is visible, so it cannot compete with
        QML loading and the first frame: tool probing, then the audio device and the
        yt-dlp import (both previously on the critical path or paid at first use)."""
        if self._is_quitting or self._startup_done:
            return
        self._startup_done = True
        self._status_allowed = True
        self.refresh_status()
        QTimer.singleShot(1500, self._warm_up)

    def _warm_up(self):
        if self._is_quitting:
            return
        self._ensure_player()  # avoids a hitch on the first Play click

        def preload():
            try:
                import importlib
                importlib.import_module("yt_dlp")  # first analyze/download no longer pays the import
            except ImportError:
                pass
            return True
        worker = FunctionWorker(preload, self)
        worker.finished.connect(self._cleanup_finished_worker)
        self._warm_worker = worker
        worker.start()

    def _on_player_state_changed(self, state):
        state_value = int(state.value if hasattr(state, "value") else state)
        self.playerChanged.emit(json.dumps({"state": state_value}))
        if state_value == _multimedia()[1].PlayingState.value:
            if not self._player_position_timer.isActive():
                self._player_position_timer.start()
        else:
            self._player_position_timer.stop()
        self._emit_player_position()

    def _emit_player_position(self):
        if self._player is not None and self._player.playbackState() == _multimedia()[1].PlayingState:
            self.playerChanged.emit(json.dumps({"position": self._player.position()}))

    def _emit_initial(self):
        self.presetsChanged.emit(json.dumps(self.presets))
        self.settingsChanged.emit(json.dumps(self.public_settings()))
        self.queueChanged.emit()
        self.statusChanged.emit(self.status_summary())
        self._emit_player_song()

    def public_settings(self):
        return {
            "output_dir": self.settings.get("output_dir", ""),
            "theme": self.settings.get("theme", "Dark"),
            "max_retries": self.settings.get("max_retries", 3),
            "fragment_concurrency": self.settings.get("fragment_concurrency", 4),
            "write_automatic_subtitles": self.settings.get("write_automatic_subtitles", False),
            "download_lyrics": bool(self.settings.get("download_lyrics", True)),
            "subtitle_languages": self.settings.get("subtitle_languages", ["all"]),
            "ffmpeg_path": self.settings.get("ffmpeg_path", ""),
            "ffprobe_path": self.settings.get("ffprobe_path", ""),
            "connection_mode": self.settings.get("connection_mode", "Automatic"),
            "proxy_url": self.settings.get("proxy_url", ""),
            "cookies_browser": self.settings.get("cookies_browser", "None"),
            "cookies_profile": self.settings.get("cookies_profile", ""),
            "recent_searches": self.settings.get("recent_searches", []),
        }

    def _persist(self):
        """Save settings without clobbering playlists, which are also written by music.py."""
        self.settings[PLAYLISTS_KEY] = self.playlists
        self.settings = save_settings(self.settings)

    def _persist_player_preferences(self):
        if self._volume_persist_timer.isActive():
            self._volume_persist_timer.stop()
        if self._audio_output is not None:
            self.settings["player_volume"] = self._audio_output.volume()
            self.settings["player_muted"] = self._audio_output.isMuted()
        self._persist()

    def _build_status_summary(self, status: dict) -> str:
        return json.dumps({
            "yt_dlp": status.get("yt_dlp") or "Missing",
            "ffmpeg": status.get("ffmpeg_version") or status.get("ffmpeg") or "Not detected",
            "ffprobe": status.get("ffprobe") or "Not detected",
            "encoders": len(status.get("encoders") or []),
            "music_download": "yt-dlp · no Spotify API credentials required",
        })

    def status_summary(self):
        """Return immediately. Tool probing (several subprocesses, up to ~17 s) used to
        run right here on the GUI thread and froze the window at start-up."""
        if self._status_cache is None:
            if self._status_allowed:
                self.refresh_status()
            return self._build_status_summary({"yt_dlp": "Checking…", "ffmpeg_version": "Checking…",
                                               "ffprobe": "Checking…", "encoders": []})
        return self._status_cache

    def refresh_status(self, force=False):
        if self._status_worker is not None and self._status_worker.isRunning():
            return
        ffmpeg = self.settings.get("ffmpeg_path") or None
        ffprobe = self.settings.get("ffprobe_path") or None
        worker = FunctionWorker(lambda: tool_status(ffmpeg, ffprobe, refresh=force), self)
        worker.done.connect(self._on_status_ready)
        worker.failed.connect(self._notify)
        worker.finished.connect(self._cleanup_finished_worker)
        self._status_worker = worker
        worker.start()

    def _on_status_ready(self, status):
        self._status_cache = self._build_status_summary(status)
        self.statusChanged.emit(self._status_cache)

    @Slot()
    def _cleanup_finished_worker(self):
        """Release completed QThreads on the GUI thread instead of retaining them until exit."""
        worker = self.sender()
        if worker is None:
            return
        for attribute in (
            "active_worker", "analysis_worker", "search_worker", "spotify_worker",
            "collection_worker", "_library_worker", "_status_worker",
            "_connection_worker", "_browser_profiles_worker", "_warm_worker",
        ):
            if getattr(self, attribute, None) is worker:
                setattr(self, attribute, None)
        worker.deleteLater()

    def _emit_queue_soon(self):
        if not self._queue_timer.isActive():
            self._queue_timer.start()

    def _notify(self, message):
        message = str(message)
        logging.getLogger(__name__).info("UI notice: %s", message[:1200])
        self.errorRaised.emit(message)

    def _new_task(self, kind, name, options=None, **fields):
        task = {
            "id": uuid.uuid4().hex[:12], "kind": kind, "name": str(name)[:180],
            "options": dict(options or {}), "output_dir": self.settings["output_dir"],
            "status": "Queued", "progress": 0, "detail": "Waiting in queue",
            "output": "", "outputs": [], **fields,
        }
        self.tasks.append(task)
        self.queueChanged.emit()
        self._process_next()
        return task

    @Slot(str, str)
    def analyzeUrl(self, url, mode="download"):
        url = str(url).strip()
        if not is_http_url(url):
            self._notify("Paste a valid http:// or https:// media URL with a hostname.")
            return
        if self.analysis_worker and self.analysis_worker.isRunning():
            self._notify("An analysis is already running.")
            return
        self._last_analysis_url = ""
        self._last_analysis = {}
        self.statusChanged.emit(json.dumps({"analysis": "Inspecting source…"}))
        self.analysis_worker = AnalyzeWorker(url, self, settings=self.settings)
        self.analysis_worker.completed.connect(lambda data: self._analysis_ready(url, data))
        self.analysis_worker.failed.connect(self.analysisFailed.emit)
        self.analysis_worker.finished.connect(self._cleanup_finished_worker)
        self.analysis_worker.start()

    def _analysis_ready(self, url, data):
        # The legacy Widgets dialog uses thumbnail_data bytes. QML loads the
        # thumbnail URL itself, so strip binary bytes before JSON serialization.
        clean = {key: value for key, value in dict(data or {}).items() if key != "thumbnail_data"}
        self._last_analysis_url = str(url)
        self._last_analysis = clean
        self.analysisReady.emit(json.dumps(clean, ensure_ascii=False))

    @Slot(str, str, str)
    def enqueueDownload(self, url, preset_name, container="Original"):
        url = str(url).strip()
        if not is_http_url(url):
            self._notify("Paste a valid http:// or https:// media URL with a hostname.")
            return
        options = dict(self.presets.get(preset_name) or self.presets.get("Balanced Quality and Size") or {})
        container = str(container or "Original").strip().lower()
        options["container"] = "original" if container == "original" else container
        media = self._last_analysis if self._last_analysis_url == url else {}
        self._new_task(
            "download", media.get("title") or url, options, url=url,
            thumbnail=media.get("thumbnail") or "",
            uploader=media.get("uploader") or media.get("channel") or "",
            duration=media.get("duration"),
            view_count=media.get("view_count"),
            upload_date=media.get("upload_date") or "",
        )

    @Slot(str)
    def enqueueSpotify(self, url):
        url = str(url).strip()
        if self.spotify_worker and self.spotify_worker.isRunning():
            self._notify("Spotify link resolution is already running.")
            return
        if not url:
            self._notify("Paste a Spotify track, album, or playlist URL.")
            return
        self.statusChanged.emit(json.dumps({"spotify": "Resolving public Spotify metadata…"}))
        self.spotify_worker = SpotifyResolveWorker(url, self)
        self.spotify_worker.completed.connect(self._spotify_resolved)
        self.spotify_worker.failed.connect(self._notify)
        self.spotify_worker.finished.connect(self._cleanup_finished_worker)
        self.spotify_worker.start()

    def _spotify_resolved(self, collection):
        tracks = collection.get("tracks") or []
        queries = [item.get("query", "").strip() for item in tracks if item.get("query", "").strip()]
        gid = uuid.uuid4().hex[:10]
        gname = str(collection.get("name") or "Spotify collection")
        gcover = str(collection.get("cover") or (tracks[0].get("cover") if tracks else "") or "")
        for track in tracks:
            query = track.get("query", "").strip()
            if query:
                self._new_task("music", query, query=query, music_track=track,
                               group_id=gid, group_name=gname, group_cover=gcover)
        message = f"Added {len(queries)} tracks from {collection.get('name', 'Spotify collection')}."
        if collection.get("limited"):
            message += " Spotify limited the public playlist response; some tracks may be missing."
        self.statusChanged.emit(json.dumps({"spotify": message}))

    @Slot(str, str, str)
    def searchMusic(self, query, provider="All catalogs", kind="All"):
        query = str(query).strip()
        if not query:
            return
        if self.search_worker and self.search_worker.isRunning():
            self._notify("A catalog search is already running.")
            return
        provider = "All" if provider in ("All catalogs", "All") else provider
        self.search_worker = CatalogSearchWorker(query, provider, kind, self)
        self.search_worker.progress.connect(lambda rows: self.searchResults.emit(json.dumps(rows)))
        self.search_worker.completed.connect(self._search_done)
        self.search_worker.failed.connect(self._search_failed)
        self.search_worker.finished.connect(self._cleanup_finished_worker)
        self.search_worker.start()

    def _search_done(self, rows):
        self.searchResults.emit(json.dumps(rows))
        self.searchFinished.emit()

    def _search_failed(self, message):
        self._notify(message)
        self.searchFinished.emit()

    @Slot(str, str)
    def openCollection(self, kind, url):
        if self.collection_worker and self.collection_worker.isRunning():
            self._notify("A collection is already being opened. Please wait for it to finish.")
            return
        self.collection_worker = CollectionWorker(str(kind), str(url), self)
        self.collection_worker.completed.connect(lambda data: self.collectionReady.emit(json.dumps(data)))
        self.collection_worker.failed.connect(self._collection_failed)
        self.collection_worker.finished.connect(self._cleanup_finished_worker)
        self.collection_worker.start()

    def _collection_failed(self, message):
        self._notify(message)
        self.collectionReady.emit("")

    @Slot(str)
    def enqueueCollection(self, payload):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return
        tracks = [t for t in (data.get("tracks") or []) if (t.get("query") or "").strip()]
        gid = uuid.uuid4().hex[:10]
        for track in tracks:
            self._new_task("music", track["query"], query=track["query"], music_track=track,
                           group_id=gid, group_name=str(data.get("name") or "Collection"),
                           group_cover=str(data.get("cover") or ""))
        self.statusChanged.emit(json.dumps({"spotify": f"Added {len(tracks)} tracks to downloads."}))

    @Slot(str, str, str)
    def enqueueMusicResult(self, title, artist, cover=""):
        query = f"{artist} - {title}".strip(" -")
        if query:
            self._new_task("music", query, query=query,
                           music_track={"title": str(title), "artist": str(artist), "cover": str(cover)})

    def _queue_music_lyrics(self, task: dict, outputs: list[str]) -> None:
        """Queue one synchronized LRC lookup for each newly downloaded audio file."""
        if not self.settings.get("download_lyrics", True):
            return
        metadata = task.get("music_track") if isinstance(task.get("music_track"), dict) else {}
        fallback_query = str(task.get("query") or task.get("name") or "").strip()
        title = str(metadata.get("title") or "").strip()
        artist = str(metadata.get("artist") or "").strip()
        if not title and " - " in fallback_query:
            artist, title = [part.strip() for part in fallback_query.split(" - ", 1)]
        elif not title:
            title = fallback_query
        album = str(metadata.get("album") or "").strip()
        try:
            duration = float(metadata.get("duration") or 0) or None
        except (TypeError, ValueError):
            duration = None

        for output in outputs or []:
            audio_path = Path(str(output)).expanduser()
            if audio_path.suffix.lower() not in AUDIO_EXTENSIONS or not audio_path.is_file():
                continue
            sidecar = audio_path.with_suffix(".lrc")
            if sidecar.exists():
                continue
            key = str(audio_path.resolve()).casefold()
            if key in self._lyrics_download_paths:
                continue
            self._lyrics_download_paths.add(key)
            self._lyrics_download_queue.append({
                "task_id": task.get("id"),
                "title": title or audio_path.stem,
                "artist": artist,
                "album": album,
                "duration": duration,
                "audio_path": str(audio_path),
                "sidecar_path": str(sidecar),
            })
        self._process_next_lyrics_download()

    def _process_next_lyrics_download(self) -> None:
        if self._lyrics_download_worker is not None:
            return
        while self._lyrics_download_queue and not self.settings.get("download_lyrics", True):
            job = self._lyrics_download_queue.pop(0)
            self._lyrics_download_paths.discard(str(Path(job["audio_path"]).resolve()).casefold())
        if not self._lyrics_download_queue:
            return
        job = self._lyrics_download_queue.pop(0)
        sidecar = Path(job["sidecar_path"])
        if sidecar.exists():
            self._lyrics_download_paths.discard(str(Path(job["audio_path"]).resolve()).casefold())
            self._process_next_lyrics_download()
            return
        worker = LyricsSearchWorker(
            job["title"],
            job["artist"],
            self,
            album=job["album"],
            duration=job["duration"],
            sidecar_path=sidecar,
        )
        self._lyrics_download_worker = worker
        worker.structuredCompleted.connect(
            lambda payload, job=job: self._on_downloaded_lyrics_ready(job, payload)
        )
        worker.failed.connect(
            lambda message, job=job: self._on_downloaded_lyrics_failed(job, message)
        )
        worker.finished.connect(
            lambda worker=worker, job=job: self._on_downloaded_lyrics_finished(worker, job)
        )
        worker.start()

    def _on_downloaded_lyrics_ready(self, job: dict, payload_text: str) -> None:
        try:
            payload = json.loads(payload_text)
        except (TypeError, json.JSONDecodeError):
            return
        local_path = str(payload.get("local_path") or "")
        task = self._find_task(str(job.get("task_id") or ""))
        if task:
            logs = task.setdefault("logs", [])
            if local_path and Path(local_path).is_file():
                logs.append(f"Saved synchronized lyrics: {Path(local_path).name}")
                task["detail"] = (task.get("detail") or "Music download complete") + " · LRC saved"
            elif payload.get("synchronized"):
                logs.append("Synchronized lyrics were found, but the LRC sidecar could not be written.")
            else:
                logs.append("No synchronized lyrics were available to save as an LRC file.")
            task["logs"] = logs[-80:]
            self._emit_queue_soon()

    def _on_downloaded_lyrics_failed(self, job: dict, message: str) -> None:
        task = self._find_task(str(job.get("task_id") or ""))
        if task:
            logs = task.setdefault("logs", [])
            logs.append("Lyrics sidecar lookup failed: " + str(message))
            task["logs"] = logs[-80:]
            self._emit_queue_soon()

    def _on_downloaded_lyrics_finished(self, worker, job: dict) -> None:
        if self._lyrics_download_worker is worker:
            self._lyrics_download_worker = None
        self._lyrics_download_paths.discard(str(Path(job["audio_path"]).resolve()).casefold())
        worker.deleteLater()
        self._process_next_lyrics_download()

    @Slot()
    def findCurrentLyrics(self):
        """Open lyrics for the loaded player item, preferring its own sidecar."""
        current = self.current_song if isinstance(self.current_song, dict) else {}
        path = str(current.get("path") or "")
        title = str(current.get("title") or "").strip()
        artist = str(current.get("artist") or "").strip()
        if not title and path and not path.startswith(("http://", "https://")):
            title = Path(path).stem
        self.findLyrics(title, artist)

    @Slot(str, str)
    def findLyrics(self, title, artist):
        title = str(title or "").strip()
        artist = str(artist or "").strip()
        if not title:
            self._notify("Choose a playing track before looking up lyrics.")
            return

        current = self.current_song if isinstance(self.current_song, dict) else {}
        current_title = str(current.get("title") or "").strip()
        current_artist = str(current.get("artist") or "").strip()
        current_path = str(current.get("path") or "")
        is_preview_url = current_path.startswith(("http://", "https://"))
        local_audio = Path(current_path).expanduser() if current_path and not is_preview_url else None

        # Display metadata can differ slightly from embedded audio tags
        # (punctuation, featuring credits, capitalization). Use a tolerant
        # identity score before considering the currently loaded local file.
        same_track = bool(current_path) and (
            title.casefold() == current_title.casefold()
            and (not artist or not current_artist or artist.casefold() == current_artist.casefold())
        )
        if not same_track and local_audio and local_audio.is_file():
            same_track = lyric_match_score(
                title, artist, current_title, current_artist
            ) >= 0.62

        if same_track and local_audio and local_audio.is_file():
            local_lrc = find_lrc_sidecar(local_audio, title, artist)
            if local_lrc is not None:
                # A sibling LRC is authoritative. Never call the online
                # providers when a local sidecar exists, even if it contains
                # plain rather than timestamped text.
                try:
                    local_text = local_lrc.read_text(encoding="utf-8-sig")
                except (OSError, UnicodeError) as exc:
                    self._notify(f"Could not read local lyrics file: {exc}")
                    return
                local_lines = parse_lrc(local_text)
                synchronized = bool(local_lines)
                if not local_lines:
                    local_lines = [
                        {"time_ms": -1, "text": line.strip()}
                        for line in local_text.splitlines()
                        if line.strip()
                        and not re.match(r"^\s*\[(?:ti|ar|al|by|length|re|ve):", line, re.IGNORECASE)
                        and not re.match(r"^\s*\[offset:", line, re.IGNORECASE)
                    ]
                self._lyrics_request_token += 1
                self.lyricsReady.emit(json.dumps({
                    "title": title or current_title,
                    "artist": artist or current_artist,
                    "request_title": title or current_title,
                    "request_artist": artist or current_artist,
                    "duration": max(0, self._duration_ms() / 1000.0),
                    "synchronized": synchronized,
                    "source": "LOCAL .LRC",
                    "sync_level": "line" if synchronized else "plain",
                    "lines": local_lines,
                    "message": "" if synchronized else "Local lyrics are not timestamped.",
                    "local_path": str(local_lrc),
                    "track_path": current_path,
                }, ensure_ascii=False))
                return

        if self.lyrics_worker and self.lyrics_worker.isRunning():
            self._notify("A lyrics lookup is already in progress.")
            return

        album = str(current.get("album") or "") if same_track else ""
        duration = max(0, self._duration_ms() / 1000.0) if same_track and not is_preview_url else None
        existing_sidecar = (
            find_lrc_sidecar(local_audio, title, artist)
            if same_track and local_audio and local_audio.is_file()
            else None
        )
        sidecar_path = (
            existing_sidecar or local_audio.with_suffix(".lrc")
            if same_track and local_audio and local_audio.is_file()
            and self.settings.get("download_lyrics", True)
            else None
        )
        self._lyrics_request_token += 1
        request_token = self._lyrics_request_token
        worker = LyricsSearchWorker(
            title, artist, self, album=album, duration=duration, sidecar_path=sidecar_path
        )
        self.lyrics_worker = worker
        worker.structuredCompleted.connect(
            lambda value, track_path=current_path, token=request_token:
                self._emit_lyrics_for_track(value, track_path, token)
        )
        worker.failed.connect(
            lambda message, token=request_token:
                self._notify(message) if token == self._lyrics_request_token else None
        )
        worker.finished.connect(lambda worker=worker: self._release_lyrics_worker(worker))
        worker.start()

    def _emit_lyrics_for_track(self, payload_text, track_path, request_token):
        """Attach the requested player item and discard stale lyric responses."""
        if request_token != self._lyrics_request_token:
            return
        try:
            payload = json.loads(payload_text)
        except (TypeError, json.JSONDecodeError):
            return
        payload["track_path"] = str(track_path or "")
        self.lyricsReady.emit(json.dumps(payload, ensure_ascii=False))

    def _release_lyrics_worker(self, worker):
        if self.lyrics_worker is worker:
            self.lyrics_worker = None
        worker.deleteLater()

    @Slot()
    def chooseConversionSource(self):
        source, _ = QFileDialog.getOpenFileName(None, "Choose media to convert", str(Path.home()), "Media files (*.*)")
        if source:
            self.conversionSourceSelected.emit(source)

    @Slot()
    def enqueueConversion(self):
        files, _ = QFileDialog.getOpenFileNames(None, "Choose media to convert", str(Path.home()), "Media files (*.*)")
        for source in files:
            self._new_task("convert", Path(source).name, {"container": "mp4", "video_codec": "h264", "audio_codec": "aac", "rate_control": "CRF", "crf": "23", "preserve_metadata": True}, source=source)

    @Slot(str, str, str, str)
    def enqueueConversionWithOptions(self, source, container, video_codec, audio_codec):
        source = str(Path(source).expanduser())
        if not Path(source).is_file():
            self._notify("Choose an existing local media file.")
            return
        options = {"container": container, "video_codec": video_codec, "audio_codec": audio_codec,
                   "rate_control": "CRF", "crf": "23", "fps": "Source", "resolution": "Source",
                   "preserve_metadata": True}
        self._new_task("convert", Path(source).name, options, source=source)

    @Slot(str)
    def cancelTask(self, task_id):
        task = self._find_task(task_id)
        if not task:
            return
        if task_id == self.active_task_id and self.active_worker:
            task["detail"] = "Cancelling…"
            self.active_worker.cancel()
        elif task["status"] == "Queued":
            task["status"] = "Cancelled"
            task["detail"] = "Cancelled before starting"
        self.queueChanged.emit()

    @Slot(str)
    def retryTask(self, task_id):
        task = self._find_task(task_id)
        if task and task["status"] in {"Failed", "Cancelled"}:
            task.update(status="Queued", progress=0, detail="Queued for retry", output="")
            self.queueChanged.emit()
            self._process_next()

    @Slot(str)
    def retryGroup(self, group_id):
        for task in self.tasks:
            if task.get("group_id") == group_id and task["status"] in {"Failed", "Cancelled"}:
                task.update(status="Queued", progress=0, detail="Queued for retry", output="")
        self.queueChanged.emit()
        self._process_next()

    @Slot(str)
    def removeGroup(self, group_id):
        """Remove a download group (or a single task id); running work is cancelled first."""
        for task in list(self.tasks):
            if task.get("group_id") == group_id or task["id"] == group_id:
                if task["status"] in {"Starting", "Running"}:
                    self.cancelTask(task["id"])
                    continue
                self.tasks.remove(task)
        self.queueChanged.emit()

    @Slot()
    def clearFinished(self):
        self.tasks = [task for task in self.tasks if task["status"] not in {"Completed", "Cancelled"}]
        self.queueChanged.emit()

    @Slot()
    def refreshQueue(self):
        self.queueChanged.emit()

    def _find_task(self, task_id):
        return next((task for task in self.tasks if task["id"] == task_id), None)

    def _process_next(self):
        # A finished worker's queued signal may be delivered while the app is
        # closing. Never start another queued operation once shutdown begins.
        if self._is_quitting or self.active_worker is not None:
            return
        task = next((item for item in self.tasks if item["status"] == "Queued"), None)
        if not task:
            self.queueChanged.emit()
            return
        task.update(status="Starting", detail="Starting local worker…")
        self.active_task_id = task["id"]
        self.queueChanged.emit()
        self.active_worker = MediaTaskWorker(task, self.settings, self)
        self.active_worker.progress.connect(self._on_progress)
        self.active_worker.log.connect(self._on_log)
        self.active_worker.completed.connect(self._on_completed)
        self.active_worker.finished.connect(self._on_worker_finished)
        self.active_worker.finished.connect(self._cleanup_finished_worker)
        self.active_worker.start()

    def _on_progress(self, task_id, percent, detail):
        task = self._find_task(task_id)
        if task:
            task.update(progress=max(0, min(100, int(percent))), detail=str(detail))
            if task["status"] in {"Queued", "Starting"}:
                task["status"] = "Running"
                self.queueChanged.emit()  # status transitions are shown immediately
            else:
                self._emit_queue_soon()

    def _on_log(self, task_id, message):
        task = self._find_task(task_id)
        message = str(message)
        if task:
            logs = task.setdefault("logs", [])
            logs.append(message)
            task["logs"] = logs[-80:]
            # Keep the global log useful even after a task card is removed.
            logging.getLogger("ums.tasks").info("[%s] %s", task_id, message)
            self.logUpdated.emit()

    def _on_completed(self, task_id, status, outputs, error):
        task = self._find_task(task_id)
        if task:
            task.update(status=status, progress=100 if status == "Completed" else task.get("progress", 0),
                        detail=error or (f"{len(outputs)} output file(s)" if outputs else status),
                        outputs=[str(path) for path in outputs],
                        output="; ".join(str(path) for path in outputs[:2]))
        self.queueChanged.emit()
        if status == "Completed" and task and task.get("kind") == "music":
            self._queue_music_lyrics(task, outputs)
            self.refreshLibrary()
        if status == "Failed":
            self._notify(error)

    def _on_worker_finished(self):
        self.active_worker = None
        self.active_task_id = None
        self.queueChanged.emit()
        self._process_next()

    def _emit_player_song(self):
        self.playerChanged.emit(json.dumps({
            "song": self.current_song,
            "state": self._player.playbackState().value if self._player is not None else 0,
            "position": self._player.position() if self._player is not None else 0,
            "duration": self._duration_ms(),
            "volume": self._audio_output.volume() if self._audio_output is not None
                      else float(self.settings.get("player_volume", 0.75)),
            "muted": self._audio_output.isMuted() if self._audio_output is not None
                     else bool(self.settings.get("player_muted", False)),
            "can_skip": bool(self.playback_queue),
            "shuffle": self.shuffle_enabled,
            "repeat": self.repeat_mode,
            "closed": not self.current_song.get("path"),
        }))

    @Slot(str, str, str, str)
    def playPreview(self, url, title, artist, cover=""):
        if not is_http_url(url):
            self._notify("This catalog item has no playable preview. Download it to play the full track.")
            return
        self.playback_queue = []
        self.ordered_queue = []
        self.playback_index = -1
        self.current_song = {"title": str(title), "artist": str(artist), "path": str(url), "cover": str(cover)}
        self.player.setSource(QUrl(str(url)))
        self.player.play()
        self._emit_player_song()

    @Slot(str, int)
    def playPreviewList(self, payload, start):
        """Play a list of catalog previews as a queue (album/playlist/artist pages)."""
        try:
            rows = json.loads(payload)
        except json.JSONDecodeError:
            return
        rows = [{"title": r.get("title") or "Unknown", "artist": r.get("artist") or "", "cover": r.get("cover") or "",
                 "path": r.get("preview") or "", "album": r.get("album") or ""}
                for r in rows if is_http_url(r.get("preview") or "")]
        if not rows:
            self._notify("None of these tracks has a playable preview. Download them to listen.")
            return
        start = max(0, min(int(start), len(rows) - 1))
        self.ordered_queue = list(rows)
        self.playback_queue = list(rows)
        self.playback_index = start
        if self.shuffle_enabled:
            self._shuffle_queue(rows[start]["path"])
        self._play_library_row(self.playback_queue[self.playback_index])

    @Slot(str)
    def playFile(self, path):
        path = str(Path(path).expanduser())
        if not Path(path).is_file():
            self._notify("The selected audio file no longer exists.")
            return
        row = next((item for item in self.library if item.get("path") == path), None)
        if not any(item.get("path") == path for item in self.playback_queue):
            self.ordered_queue = list(self.library)
            self.playback_queue = list(self.library)
            if self.shuffle_enabled:
                self._shuffle_queue(path)
        self.playback_index = next((i for i, item in enumerate(self.playback_queue) if item.get("path") == path), -1)
        self._play_library_row(row or {"path": path, "title": Path(path).stem, "artist": "Local library"})

    def _play_library_row(self, row):
        raw = str(row.get("path", ""))
        if is_http_url(raw):
            self.current_song = {"title": row.get("title") or "Unknown", "artist": row.get("artist") or "",
                                 "album": row.get("album") or "", "cover": row.get("cover") or "", "path": raw}
            self.player.setSource(QUrl(raw))
            self.player.play()
            self._emit_player_song()
            return
        path = str(Path(raw).expanduser())
        if not Path(path).is_file():
            self._notify("The selected audio file no longer exists.")
            return
        self.current_song = {
            "title": row.get("title") or Path(path).stem,
            "artist": row.get("artist") or "Unknown artist",
            "album": row.get("album") or "",
            "cover": row.get("cover") or "",
            "path": path,
        }
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
        self._emit_player_song()

    @Slot()
    def playNext(self):
        self._advance(auto=False)

    def _advance(self, auto):
        if not self.playback_queue or self.playback_index < 0:
            return
        next_index = self.playback_index + 1
        if next_index >= len(self.playback_queue):
            if auto and self.repeat_mode == 0:
                self.player.stop()
                self._emit_player_song()
                return
            next_index = 0
        self.playback_index = next_index
        self._play_library_row(self.playback_queue[self.playback_index])

    @Slot()
    def playPrevious(self):
        if not self.playback_queue or self.playback_index < 0:
            return
        if self.player.position() > 3000:
            self.player.setPosition(0)
            return
        self.playback_index = self.playback_index - 1 if self.playback_index > 0 else len(self.playback_queue) - 1
        self._play_library_row(self.playback_queue[self.playback_index])

    def _on_media_status(self, status):
        if status != _multimedia()[1].EndOfMedia:
            return
        if self.repeat_mode == 2:
            self.player.setPosition(0)
            self.player.play()
        elif self.playback_queue and self.playback_index >= 0:
            self._advance(auto=True)

    def _shuffle_queue(self, first_path=None):
        import random
        rows = list(self.ordered_queue or self.playback_queue)
        first_path = first_path or self.current_song.get("path")
        first = next((r for r in rows if r.get("path") == first_path), None)
        rest = [r for r in rows if r is not first]
        random.shuffle(rest)
        self.playback_queue = ([first] if first else []) + rest
        self.playback_index = 0 if first else (0 if self.playback_queue else -1)

    @Slot()
    def toggleShuffle(self):
        self.shuffle_enabled = not self.shuffle_enabled
        self.settings["player_shuffle"] = self.shuffle_enabled
        self._persist()
        if self.playback_queue:
            current = self.current_song.get("path")
            if self.shuffle_enabled:
                if not self.ordered_queue:
                    self.ordered_queue = list(self.playback_queue)
                self._shuffle_queue(current)
            elif self.ordered_queue:
                self.playback_queue = list(self.ordered_queue)
                self.playback_index = next((i for i, r in enumerate(self.playback_queue) if r.get("path") == current), 0)
        self._emit_player_song()

    @Slot()
    def cycleRepeat(self):
        self.repeat_mode = (self.repeat_mode + 1) % 3
        self.settings["player_repeat"] = self.repeat_mode
        self._persist()
        self._emit_player_song()

    @Slot()
    def closePlayer(self):
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())
        self.current_song = {}
        self.playback_queue = []
        self.ordered_queue = []
        self.playback_index = -1
        self._emit_player_song()
        self.playerChanged.emit(json.dumps({"position": 0, "duration": 0, "state": 0}))

    @Slot()
    def playAllLibrary(self):
        if not self.library and not self._library_loaded:
            self._scan_library(then=self.playAllLibrary)
            return
        self.ordered_queue = list(self.library)
        self.playback_queue = list(self.library)
        if self.shuffle_enabled:
            self._shuffle_queue(self.playback_queue[0].get("path") if self.playback_queue else None)
        self.playback_index = 0 if self.playback_queue else -1
        if self.playback_queue:
            self._play_library_row(self.playback_queue[0])

    @Slot()
    def shuffleLibrary(self):
        import random
        self.ordered_queue = list(self.library)
        self.playback_queue = list(self.library)
        random.shuffle(self.playback_queue)
        self.shuffle_enabled = True
        self.settings["player_shuffle"] = True
        self._persist()
        self.playback_index = 0 if self.playback_queue else -1
        if self.playback_queue:
            self._play_library_row(self.playback_queue[0])

    @Slot(str)
    def playPlaylist(self, name):
        paths = self.playlists.get(str(name), [])
        lookup = {row.get("path"): row for row in self.library}
        self.playback_queue = [lookup[path] for path in paths if path in lookup and Path(path).is_file()]
        self.ordered_queue = list(self.playback_queue)
        if self.shuffle_enabled and self.playback_queue:
            self._shuffle_queue(self.playback_queue[0].get("path"))
        self.playback_index = 0 if self.playback_queue else -1
        if self.playback_queue:
            self._play_library_row(self.playback_queue[0])
        else:
            self._notify("This playlist has no available local audio files.")

    @Slot()
    def togglePlayback(self):
        if not self.current_song.get("path"):
            self._notify("Choose a song from your library first.")
            return
        if self.player.playbackState() == _multimedia()[1].PlayingState:
            self.player.pause()
        else:
            self.player.play()
        self._emit_player_song()

    @Slot(int)
    def seekPlayer(self, position):
        """Seek the existing player and resume playback from the selected lyric."""
        if not self.current_song.get("path"):
            self._notify("Choose a song before seeking.")
            return
        target = max(0, int(position))
        self.player.setPosition(target)
        # Clicking a lyric is a play action as well as a seek action. Resume
        # paused/finished playback without creating or replacing a player.
        if self.player.playbackState() != _multimedia()[1].PlayingState:
            self.player.play()
        # Publish the requested position immediately; multimedia backends may
        # report their next positionChanged event a little later.
        self.playerChanged.emit(json.dumps({"position": target}))

    @Slot()
    def stopPlayback(self):
        self.player.stop()
        self.playerChanged.emit(json.dumps({"state": int(self.player.playbackState().value), "position": 0}))

    @Slot()
    def toggleMute(self):
        self.audio_output.setMuted(not self.audio_output.isMuted())
        self.settings["player_muted"] = self.audio_output.isMuted()
        self._persist_player_preferences()
        self.playerChanged.emit(json.dumps({"muted": self.audio_output.isMuted(), "volume": self.audio_output.volume()}))

    @Slot(float)
    def setVolume(self, volume):
        value = max(0.0, min(1.0, float(volume)))
        self.audio_output.setVolume(value)
        self.settings["player_volume"] = value
        self._volume_persist_timer.start()
        self.playerChanged.emit(json.dumps({"volume": self.audio_output.volume(), "muted": self.audio_output.isMuted()}))

    @Slot(str, str)
    def addFileToPlaylist(self, name, path):
        name = str(name).strip() or "Favorites"
        path = str(Path(path).expanduser())
        if not Path(path).is_file():
            self._notify("The selected audio file no longer exists.")
            return
        self.playlists.setdefault(name, [])
        if path not in self.playlists[name]:
            self.playlists[name].append(path)
            save_music_playlists(self.playlists)
            self.playlistsChanged.emit(json.dumps(self.playlists))

    @Slot(str)
    def removePlaylist(self, name):
        self.playlists.pop(str(name), None)
        save_music_playlists(self.playlists)
        self.playlistsChanged.emit(json.dumps(self.playlists))

    @Slot(result=str)
    def logPath(self):
        """Return the path of the rotating application log."""
        return str(LOG_FILE)

    def _read_log_text(self, max_chars=8 * 1024 * 1024):
        # Include rotated files oldest-to-newest. The viewer uses a smaller cap
        # than export so opening the dialog stays responsive on slower machines.
        paths = [
            LOG_FILE.with_name(LOG_FILE.name + f".{index}")
            for index in range(LOG_BACKUP_COUNT, 0, -1)
        ] + [LOG_FILE]
        chunks = []
        for path in paths:
            try:
                if path.is_file():
                    chunks.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:
                logging.getLogger(__name__).warning("Could not read log %s: %s", path, exc)
        output = "\n".join(part.rstrip() for part in chunks if part.strip())
        if not output:
            return "No application log has been written yet."
        if len(output) > max_chars:
            output = "[Earlier log output omitted to keep this view bounded.]\n" + output[-max_chars:]
        return output

    @Slot(result=str)
    def readLog(self):
        """Return recent application and task diagnostics for the in-app viewer."""
        return self._read_log_text(max_chars=250_000)

    @Slot()
    def openLogFile(self):
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            LOG_FILE.touch(exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_FILE))):
                self._notify("Could not open the application log with the default text editor.")
        except OSError as exc:
            logging.getLogger(__name__).exception("Could not open the application log")
            self._notify(f"Could not open application log: {exc}")

    @Slot()
    def exportLog(self):
        suggested = Path.home() / "Downloads" / "UMS-application-log.txt"
        destination, _ = QFileDialog.getSaveFileName(
            None,
            "Export application log",
            str(suggested),
            "Text files (*.txt);;Log files (*.log);;All files (*)",
        )
        if not destination:
            return
        try:
            Path(destination).expanduser().write_text(
                self._read_log_text(max_chars=8 * 1024 * 1024),
                encoding="utf-8",
            )
        except OSError as exc:
            logging.getLogger(__name__).exception("Could not export the application log")
            self._notify(f"Could not export application log: {exc}")
            return
        logging.getLogger(__name__).info("Application log exported")
        self._notify(f"Application log exported to {destination}")

    @Slot(str)
    def openCatalogUrl(self, url):
        value = str(url).strip()
        if is_http_url(value):
            QDesktopServices.openUrl(QUrl(value))
        else:
            self._notify("This catalog result does not include a valid page URL.")

    @Slot(str)
    def openPath(self, path):
        path = str(path)
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @Slot()
    def openOutputFolder(self):
        path = Path(self.settings["output_dir"]).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        self.openPath(str(path))

    @Slot()
    def chooseOutputFolder(self):
        folder = QFileDialog.getExistingDirectory(None, "Choose downloads folder", self.settings["output_dir"])
        if folder:
            self.setSetting("output_dir", folder)

    @Slot(str, str)
    def setSetting(self, key, value):
        allowed = {"output_dir", "theme", "ffmpeg_path", "ffprobe_path", "connection_mode", "proxy_url", "cookies_browser", "cookies_profile", "download_lyrics"}
        if key not in allowed:
            self._notify(f"Setting cannot be changed here: {key}")
            return
        if key == "download_lyrics":
            enabled = str(value).strip().lower() in {"1", "true", "yes", "on"}
            self.settings[key] = enabled
            if not enabled:
                for job in self._lyrics_download_queue:
                    key_path = str(Path(job["audio_path"]).resolve()).casefold()
                    self._lyrics_download_paths.discard(key_path)
                self._lyrics_download_queue.clear()
        else:
            self.settings[key] = str(value)
        self._persist()
        if key in {"ffmpeg_path", "ffprobe_path"}:
            self._status_cache = None
            self.refresh_status()
        self.settingsChanged.emit(json.dumps(self.public_settings()))

    @Slot(str)
    def setRecentSearches(self, payload):
        try:
            values = [str(v)[:200] for v in json.loads(payload)][:8]
        except (json.JSONDecodeError, TypeError):
            return
        self.settings["recent_searches"] = values
        self._persist()
        self.settingsChanged.emit(json.dumps(self.public_settings()))

    @Slot(str)
    def setSettingJson(self, payload):
        try:
            values = json.loads(payload)
        except json.JSONDecodeError:
            self._notify("Invalid settings data.")
            return
        for key in ("output_dir", "theme", "max_retries", "fragment_concurrency", "write_automatic_subtitles", "download_lyrics", "subtitle_languages", "ffmpeg_path", "ffprobe_path", "connection_mode", "proxy_url", "cookies_browser", "cookies_profile", "recent_searches"):
            if key in values:
                self.settings[key] = values[key]
        self._persist()
        self.settingsChanged.emit(json.dumps(self.public_settings()))
        self._status_cache = None
        self.refresh_status()

    @Slot()
    def refreshLibrary(self):
        self._scan_library()

    def _scan_library(self, then=None):
        """Scan on a worker thread (tag parsing used to block the GUI thread)."""
        if then is not None:
            self._library_waiters.append(then)
        if self._library_scanning:
            self._library_rescan = True  # something changed mid-scan; scan again afterwards
            return
        self._library_scanning = True
        root = self.settings.get("output_dir", "")
        worker = FunctionWorker(lambda: scan_audio_library(root), self)
        worker.done.connect(self._on_library_scanned)
        worker.failed.connect(self._on_library_failed)
        worker.finished.connect(self._cleanup_finished_worker)
        self._library_worker = worker
        worker.start()

    def _on_library_failed(self, message):
        self._library_scanning = False
        self._library_loaded = True
        self._notify(f"Library scan failed: {message}")
        self._run_library_waiters()

    def _on_library_scanned(self, rows):
        self._library_scanning = False
        self._library_loaded = True
        self.library = rows
        if self.playback_queue:
            # Keep playback order (shuffle) and remote previews; just refresh local rows.
            fresh = {row["path"]: row for row in rows}
            current = self.current_song.get("path")
            self.playback_queue = [fresh.get(item.get("path"), item) for item in self.playback_queue
                                   if item.get("path") in fresh or is_http_url(item.get("path", ""))]
            self.playback_index = next((i for i, item in enumerate(self.playback_queue) if item.get("path") == current),
                                       min(self.playback_index, len(self.playback_queue) - 1))
        self.libraryChanged.emit(json.dumps(self.library))
        if self._library_rescan:
            self._library_rescan = False
            self._scan_library()
            return
        self._run_library_waiters()

    def _run_library_waiters(self):
        waiters, self._library_waiters = self._library_waiters, []
        for callback in waiters:
            callback()

    @Slot()
    def refreshPlaylists(self):
        self.playlists = load_music_playlists()
        self.playlistsChanged.emit(json.dumps(self.playlists))

    @Slot(str, str)
    def createPlaylist(self, name, paths_json):
        name = str(name).strip()
        try:
            paths = json.loads(paths_json or "[]")
        except json.JSONDecodeError:
            paths = []
        if not name:
            self._notify("Enter a playlist name.")
            return
        self.playlists[name] = [str(path) for path in paths]
        save_music_playlists(self.playlists)
        self.playlistsChanged.emit(json.dumps(self.playlists))

    @Slot(str)
    def addToPlaylist(self, name):
        if not self.library and not self._library_loaded:
            self._scan_library(then=lambda: self.addToPlaylist(name))
            return
        if not name:
            return
        self.playlists.setdefault(name, [])
        self.playlists[name].extend(row["path"] for row in self.library if row["path"] not in self.playlists[name])
        save_music_playlists(self.playlists)
        self.playlistsChanged.emit(json.dumps(self.playlists))

    def _detect_browser_profiles(self):
        """Return only Chromium/Firefox profiles that exist on this machine."""
        home = Path.home()
        import platform
        system = platform.system()
        found = []
        def add(browser, label, profile):
            path = Path(profile).expanduser()
            if path.is_dir():
                found.append({"browser": browser, "label": label, "profile": str(path)})

        if system == "Windows":
            local = Path.home() / "AppData/Local"
            roaming = Path.home() / "AppData/Roaming"
            roots = [
                ("brave", "Brave", local / "BraveSoftware/Brave-Browser/User Data"),
                ("chrome", "Chrome", local / "Google/Chrome/User Data"),
                ("edge", "Edge", local / "Microsoft/Edge/User Data"),
                ("firefox", "Firefox", roaming / "Mozilla/Firefox"),
            ]
        elif system == "Darwin":
            roots = [
                ("brave", "Brave", home / "Library/Application Support/BraveSoftware/Brave-Browser"),
                ("chrome", "Chrome", home / "Library/Application Support/Google/Chrome"),
                ("edge", "Edge", home / "Library/Application Support/Microsoft Edge"),
                ("firefox", "Firefox", home / "Library/Application Support/Firefox"),
            ]
        else:
            roots = [
                ("brave", "Brave", home / ".config/BraveSoftware/Brave-Browser"),
                ("chrome", "Chrome", home / ".config/google-chrome"),
                ("chromium", "Chromium", home / ".config/chromium"),
                ("edge", "Edge", home / ".config/microsoft-edge"),
                ("firefox", "Firefox", home / ".mozilla/firefox"),
            ]

        for browser, label, root in roots:
            if not root.is_dir():
                continue
            if browser == "firefox":
                ini = root / "profiles.ini"
                if ini.is_file():
                    import configparser
                    parser = configparser.ConfigParser()
                    try:
                        parser.read(ini, encoding="utf-8")
                        for section in parser.sections():
                            if not section.lower().startswith("profile"):
                                continue
                            raw = parser.get(section, "Path", fallback="")
                            if not raw:
                                continue
                            relative = parser.getboolean(section, "IsRelative", fallback=True)
                            profile = (root / raw) if relative else Path(raw)
                            if profile.is_dir() and (profile / "cookies.sqlite").is_file():
                                name = parser.get(section, "Name", fallback=profile.name)
                                add(browser, f"{label} · {name}", profile)
                    except (OSError, configparser.Error, ValueError):
                        pass
                else:
                    for profile in root.glob("*.default*"):
                        if (profile / "cookies.sqlite").is_file():
                            add(browser, f"{label} · {profile.name}", profile)
            else:
                # Chromium browsers keep profiles below the user-data root.
                candidates = [root / "Default", *root.glob("Profile *")]
                for profile in candidates:
                    if (profile / "Network/Cookies").is_file() or (profile / "Cookies").is_file():
                        suffix = "" if profile.name == "Default" else f" · {profile.name}"
                        add(browser, f"{label}{suffix}", profile)
        return found

    @Slot(result=str)
    def browserProfilesJson(self):
        return json.dumps(self._detect_browser_profiles())

    @Slot()
    def refreshBrowserProfiles(self):
        if self._browser_profiles_worker and self._browser_profiles_worker.isRunning():
            return
        worker = FunctionWorker(self._detect_browser_profiles, self)
        worker.done.connect(lambda rows: self.statusChanged.emit(json.dumps({"browser_profiles": rows})))
        worker.failed.connect(lambda message: self._notify(f"Could not inspect browser profiles: {message}"))
        worker.finished.connect(self._cleanup_finished_worker)
        self._browser_profiles_worker = worker
        worker.start()

    @Slot(result=str)
    def detectedProxy(self):
        import urllib.request
        proxies = urllib.request.getproxies()
        return proxies.get("https") or proxies.get("http") or "No system proxy set — connecting directly."

    @Slot()
    def testConnection(self):
        # Blocking network I/O (up to 8 s) must not run on the GUI thread.
        if self._connection_worker is not None and self._connection_worker.isRunning():
            return
        mode = str(self.settings.get("connection_mode") or "Automatic").lower()
        proxy = str(self.settings.get("proxy_url") or "").strip()

        def probe():
            import urllib.request
            if mode == "direct":
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            elif mode == "proxy":
                if not proxy:
                    raise ValueError("Enter a proxy URL first.")
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
            else:
                opener = urllib.request.build_opener()
            with opener.open("https://www.youtube.com/generate_204", timeout=8) as response:
                return "Connection test passed (HTTP %s)." % response.status

        worker = FunctionWorker(probe, self)
        worker.done.connect(self._notify)
        worker.failed.connect(lambda message: self._notify("Connection test failed: %s" % message))
        worker.finished.connect(self._cleanup_finished_worker)
        self._connection_worker = worker
        worker.start()

    @Slot()
    def findProxyHelp(self):
        self._notify("System proxy: " + self.detectedProxy() + " VPN proxy details are usually shown in your VPN app under Settings → Connection or Proxy.")

    @Slot()
    def checkForUpdates(self):
        QDesktopServices.openUrl(QUrl("https://github.com/mhhanzala12/UMS-siga/releases"))

    @Slot()
    def diagnostics(self):
        self.refresh_status(force=True)  # result arrives through statusChanged

    @Slot()
    def quit(self):
        if self._is_quitting:
            return
        self._is_quitting = True
        self._player_position_timer.stop()
        if self._volume_persist_timer.isActive():
            self._persist_player_preferences()
        if self._player is not None:
            self._player.stop()
        self._lyrics_download_queue.clear()

        # Stop every owned worker before Qt destroys the bridge. yt-dlp, FFmpeg,
        # and provider requests all have bounded socket/process timeouts; waiting
        # avoids QThread-destroyed-while-running crashes and orphaned subprocesses.
        workers = (
            self.active_worker, self.analysis_worker, self.search_worker,
            self.spotify_worker, self.lyrics_worker, self._lyrics_download_worker,
            self.collection_worker, self._library_worker, self._status_worker,
            self._connection_worker, self._browser_profiles_worker, self._warm_worker,
        )
        unique_workers = {id(worker): worker for worker in workers if worker is not None}
        for worker in unique_workers.values():
            if worker.isRunning():
                cancel = getattr(worker, "cancel", None)
                if callable(cancel):
                    cancel()
        for worker in unique_workers.values():
            if worker.isRunning():
                worker.wait()


    @Slot(result=str)
    def queueJson(self):
        return json.dumps([{key: task[key] for key in _QUEUE_FIELDS if key in task} for task in self.tasks])

    @Slot(result=str)
    def presetsJson(self):
        return json.dumps(self.presets)

    @Slot(result=str)
    def settingsJson(self):
        return json.dumps(self.public_settings())

    @Slot(result=str)
    def libraryJson(self):
        return json.dumps(self.library)

    @Slot(result=str)
    def playlistsJson(self):
        return json.dumps(self.playlists)

    @Slot(result=str)
    def statusJson(self):
        return self.status_summary()
