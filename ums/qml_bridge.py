"""Qt/QML bridge for the modern Universal Media Studio desktop interface.

The bridge delegates media work to the existing engine and workers. It never
runs downloads, conversions, catalog requests, or Spotify resolution on the
GUI thread.
"""
from __future__ import annotations

import json
import uuid
import urllib.request
import configparser
import platform
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QFileDialog

from .config import load_settings, save_settings
from .engine import tool_status
from .music import (
    CatalogSearchWorker, CollectionWorker, LyricsSearchWorker, SpotifyResolveWorker,
    PLAYLISTS_KEY, load_music_playlists, save_music_playlists, scan_audio_library,
)
from .presets import merged_presets
from .workers import AnalyzeWorker, FunctionWorker, MediaTaskWorker

# Only the fields the QML queue/downloads view reads. The old queueJson() also
# serialised every task's options dict and up to 80 log lines on each update.
_QUEUE_FIELDS = ("id", "kind", "name", "status", "progress", "detail", "output", "outputs",
                 "group_id", "group_name", "group_cover", "music_track")
QUEUE_EMIT_INTERVAL_MS = 150


class AppBridge(QObject):
    queueChanged = Signal()
    statusChanged = Signal(str)
    analysisReady = Signal(str)
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
        self.search_worker = None
        self.spotify_worker = None
        self.lyrics_worker = None
        self.collection_worker = None
        self.library = []
        self._library_loaded = False
        self._library_scanning = False
        self._library_rescan = False
        self._library_waiters: list = []
        self._library_worker = None
        self._status_cache: str | None = None
        self._status_worker = None
        self._connection_worker = None
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
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(max(0.0, min(1.0, float(self.settings.get("player_volume", 0.75)))))
        self.audio_output.setMuted(bool(self.settings.get("player_muted", False)))
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.positionChanged.connect(lambda value: self.playerChanged.emit(json.dumps({"position": value})))
        self.player.durationChanged.connect(lambda value: self.playerChanged.emit(json.dumps({"duration": value})))
        self.player.playbackStateChanged.connect(lambda value: self.playerChanged.emit(json.dumps({"state": int(value)})))
        self._emit_initial()

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
        save_settings(self.settings)

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
        self._status_worker = worker
        worker.start()

    def _on_status_ready(self, status):
        self._status_cache = self._build_status_summary(status)
        self.statusChanged.emit(self._status_cache)

    def _emit_queue_soon(self):
        if not self._queue_timer.isActive():
            self._queue_timer.start()

    def _notify(self, message):
        self.errorRaised.emit(str(message))

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
        if not url.startswith(("https://", "http://")):
            self._notify("Paste a complete http:// or https:// media URL.")
            return
        if self.analysis_worker and self.analysis_worker.isRunning():
            self._notify("An analysis is already running.")
            return
        self.statusChanged.emit(json.dumps({"analysis": "Inspecting source…"}))
        self.analysis_worker = AnalyzeWorker(url, self, settings=self.settings)
        self.analysis_worker.completed.connect(lambda data: self.analysisReady.emit(json.dumps(data)))
        self.analysis_worker.failed.connect(self._notify)
        self.analysis_worker.start()

    @Slot(str, str, str)
    def enqueueDownload(self, url, preset_name, container="Original"):
        url = str(url).strip()
        if not url.startswith(("https://", "http://")):
            self._notify("Paste a complete media URL first.")
            return
        options = dict(self.presets.get(preset_name) or self.presets.get("Balanced Quality and Size") or {})
        container = str(container or "Original").strip().lower()
        options["container"] = "original" if container == "original" else container
        self._new_task("download", url, options, url=url)

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
            self.collection_worker.wait(300)
        self.collection_worker = CollectionWorker(str(kind), str(url), self)
        self.collection_worker.completed.connect(lambda data: self.collectionReady.emit(json.dumps(data)))
        self.collection_worker.failed.connect(self._collection_failed)
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

    @Slot(str, str)
    def findLyrics(self, title, artist):
        if self.lyrics_worker and self.lyrics_worker.isRunning():
            return
        self.lyrics_worker = LyricsSearchWorker(str(title), str(artist), self)
        self.lyrics_worker.completed.connect(self.lyricsReady.emit)
        self.lyrics_worker.failed.connect(self._notify)
        self.lyrics_worker.start()

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
        if self.active_worker is not None:
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
        if task:
            logs = task.setdefault("logs", [])
            logs.append(str(message))
            task["logs"] = logs[-80:]

    def _on_completed(self, task_id, status, outputs, error):
        task = self._find_task(task_id)
        if task:
            task.update(status=status, progress=100 if status == "Completed" else task.get("progress", 0),
                        detail=error or (f"{len(outputs)} output file(s)" if outputs else status),
                        outputs=[str(path) for path in outputs],
                        output="; ".join(str(path) for path in outputs[:2]))
        self.queueChanged.emit()
        if status == "Completed" and task and task.get("kind") == "music":
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
            "state": self.player.playbackState().value,
            "position": self.player.position(),
            "duration": self.player.duration(),
            "volume": self.audio_output.volume(),
            "muted": self.audio_output.isMuted(),
            "can_skip": bool(self.playback_queue),
            "shuffle": self.shuffle_enabled,
            "repeat": self.repeat_mode,
            "closed": not self.current_song.get("path"),
        }))

    @Slot(str, str, str, str)
    def playPreview(self, url, title, artist, cover=""):
        if not str(url).startswith(("https://", "http://")):
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
                for r in rows if str(r.get("preview") or "").startswith(("https://", "http://"))]
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
        if raw.startswith(("https://", "http://")):
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
        if status != QMediaPlayer.EndOfMedia:
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
        self.player.stop()
        self.player.setSource(QUrl())
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
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()
        self._emit_player_song()

    @Slot(int)
    def seekPlayer(self, position):
        self.player.setPosition(int(position))

    @Slot()
    def stopPlayback(self):
        self.player.stop()
        self.playerChanged.emit(json.dumps({"state": int(self.player.playbackState()), "position": 0}))

    @Slot()
    def toggleMute(self):
        self.audio_output.setMuted(not self.audio_output.isMuted())
        self.settings["player_muted"] = self.audio_output.isMuted()
        self._persist()
        self.playerChanged.emit(json.dumps({"muted": self.audio_output.isMuted(), "volume": self.audio_output.volume()}))

    @Slot(float)
    def setVolume(self, volume):
        value = max(0.0, min(1.0, float(volume)))
        self.audio_output.setVolume(value)
        self.settings["player_volume"] = value
        self._persist()
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

    @Slot(str)
    def openCatalogUrl(self, url):
        value = str(url).strip()
        if value.startswith(("https://", "http://")):
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
        allowed = {"output_dir", "theme", "ffmpeg_path", "ffprobe_path", "connection_mode", "proxy_url", "cookies_browser", "cookies_profile"}
        if key not in allowed:
            self._notify(f"Setting cannot be changed here: {key}")
            return
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
        for key in ("output_dir", "theme", "max_retries", "fragment_concurrency", "write_automatic_subtitles", "subtitle_languages", "ffmpeg_path", "ffprobe_path", "connection_mode", "proxy_url", "cookies_browser", "cookies_profile", "recent_searches"):
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
                                   if item.get("path") in fresh or str(item.get("path", "")).startswith(("http://", "https://"))]
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
        self.statusChanged.emit(json.dumps({"browser_profiles": self._detect_browser_profiles()}))

    @Slot(result=str)
    def detectedProxy(self):
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
        self._connection_worker = worker
        worker.start()

    @Slot()
    def findProxyHelp(self):
        self._notify("System proxy: " + self.detectedProxy() + " VPN proxy details are usually shown in your VPN app under Settings → Connection or Proxy.")

    @Slot()
    def checkForUpdates(self):
        QDesktopServices.openUrl(QUrl("https://github.com/mhhanzala12/MEDIA-DOWNLOADER-APP/releases"))

    @Slot()
    def diagnostics(self):
        self.refresh_status(force=True)  # result arrives through statusChanged

    @Slot()
    def quit(self):
        self.player.stop()
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.cancel()
            self.active_worker.wait(4000)


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
