from __future__ import annotations

import logging
import threading
from typing import Callable

from PySide6.QtCore import QThread, Signal

from .engine import CancelledError, analyze_url, convert_file, download_and_process
from .music import run_music_download


class FunctionWorker(QThread):
    """Run any blocking callable off the GUI thread and report its result by signal."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object], parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
        except Exception as exc:
            logging.getLogger(__name__).exception("Background function worker failed")
            self.failed.emit(str(exc))
        else:
            self.done.emit(result)


class AnalyzeWorker(QThread):
    """Analyze source metadata and preview image away from the GUI thread.

    Thumbnail selection and fetching are handled by analyze_url(), ensuring that
    the preview fallback list and the returned bytes belong to the same analysis.
    """

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str, parent=None, settings=None):
        super().__init__(parent)
        self.url = str(url or "").strip()
        self.settings = dict(settings or {})
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            info = analyze_url(self.url, self.cancel_event, self.settings)
            if self.cancel_event.is_set():
                raise CancelledError("Analysis cancelled.")
            self.completed.emit(info)
        except CancelledError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            logging.getLogger(__name__).exception("URL analysis worker failed")
            self.failed.emit(str(exc))


class MediaTaskWorker(QThread):
    progress = Signal(str, int, str)
    log = Signal(str, str)
    completed = Signal(str, str, object, str)

    def __init__(self, task: dict, settings: dict, parent=None):
        super().__init__(parent)
        # Snapshot mutable bridge state before entering the worker thread.
        self.task = dict(task)
        self.task["options"] = dict(task.get("options") or {})
        if isinstance(task.get("music_track"), dict):
            self.task["music_track"] = dict(task["music_track"])
        self.settings = dict(settings or {})
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def _progress(self, pct, label):
        self.progress.emit(self.task["id"], int(pct), str(label))

    def _log(self, message):
        self.log.emit(self.task["id"], str(message))

    def run(self):
        task_id = self.task["id"]
        try:
            options = dict(self.task.get("options") or {})
            ffmpeg_path = self.settings.get("ffmpeg_path") or None
            ffprobe_path = self.settings.get("ffprobe_path") or None
            if self.task["kind"] == "music":
                outputs = run_music_download(
                    self.task.get("query") or self.task.get("url") or "",
                    self.task["output_dir"],
                    self.cancel_event,
                    self._progress,
                    self._log,
                    ffmpeg_path,
                    self.task.get("music_track"),
                    self.settings,
                )
            elif self.task["kind"] == "download":
                outputs = download_and_process(
                    self.task["url"],
                    self.task["output_dir"],
                    options,
                    task_id,
                    self.cancel_event,
                    self._progress,
                    self._log,
                    ffmpeg_path,
                    ffprobe_path,
                    self.settings,
                )
            else:
                output = convert_file(
                    self.task["source"],
                    self.task["output_dir"],
                    options,
                    task_id,
                    self.cancel_event,
                    self._progress,
                    self._log,
                    ffmpeg_path,
                    ffprobe_path,
                )
                outputs = [output]
            self.completed.emit(task_id, "Completed", [str(path) for path in outputs], "")
        except CancelledError as exc:
            self.completed.emit(task_id, "Cancelled", [], str(exc))
        except Exception as exc:
            logging.getLogger(__name__).exception("Media task %s failed", task_id)
            message = str(exc)
            self._log(message)
            status = "Cancelled" if self.cancel_event.is_set() else "Failed"
            self.completed.emit(task_id, status, [], message)
