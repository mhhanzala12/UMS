# Optimization notes

Every change below was made because of a measurable cost or a concrete bug found while reading the code.
Public function signatures and every QML-facing slot/signal are unchanged, so `Main.qml` and the legacy `ui.py` keep working.

## 1. GUI thread no longer blocks

| Where | Problem | Fix |
|---|---|---|
| `qml_bridge.status_summary()` | Ran `ffmpeg -version` + `ffmpeg -encoders` (timeouts 5 s + 12 s) **on the GUI thread** at start-up, on every settings save, and on every diagnostics refresh. | Returns instantly (cached or "Checking…"); probing runs in a `FunctionWorker` and arrives through `statusChanged`. |
| `engine.tool_status()` / `_run_ffmpeg()` | The encoder list was re-probed for *every* conversion. | `ffmpeg_info()` caches version + encoders per `(path, mtime)`; both probes run concurrently. Failed probes are never cached. |
| `qml_bridge.refreshLibrary()` | Walked the library and parsed tags/artwork with mutagen (two opens per file) on the GUI thread, once per finished music download. | Scan runs in a worker; overlapping requests collapse into one follow-up rescan. |
| `qml_bridge.testConnection()` | Up to 8 s of blocking network I/O on the GUI thread. | Runs in a worker. |

## 2. Fewer, cheaper UI updates

* `queueChanged` was emitted on **every** yt-dlp progress hook, and QML re-parses the whole queue and rebuilds the group model each time. Progress updates are now coalesced (150 ms single-shot timer); state transitions still emit immediately.
* `queueJson()` serialised each task's full `options` dict and up to 80 log lines that the UI never reads. It now sends only the fields `Main.qml` uses.
* yt-dlp progress hooks (download and music) are throttled to a changed percentage or one label refresh per second.

## 3. Library scan

* Persistent cache (`library_cache.json`) keyed by `(path, mtime_ns, size)`: unchanged files cost one `os.stat`. Measured on a 3-file test library: cold 36 ms, warm < 1 ms. The difference grows linearly with library size.
* Artwork is content-addressed (hash of image bytes only), so all tracks of an album share one cover file instead of one copy each.
* `os.walk` + one `stat` per file instead of `rglob` + `is_file()` + `stat()`.

## 4. Network

* `search_catalog()` queried Deezer, iTunes, YouTube and SoundCloud **sequentially**; `CatalogSearchWorker` then ran four search stages sequentially on top of that. Both now run concurrently (cost = slowest request instead of the sum). Result ordering stays deterministic. With mocked 0.3 s providers, four providers finish in 0.3 s.
* `_get_json()` has a 120 s TTL cache, so re-opening an album/playlist or repeating a search is free.
* Music matching used `ytsearch5:` with full extraction, which resolves all five videos before ranking. It now uses flat extraction (one request) for ranking and only fully resolves the chosen video. Scores are computed once rather than twice.
* Cover art is downloaded once per track instead of once per output file.

## 5. Filesystem work

* `run_music_download()` snapshotted the entire music folder (`rglob` + `stat`) **before and after** every track. It now reads the exact output paths from yt-dlp's `requested_downloads`, with a cheap mtime-based fallback.
* `download_and_process()` walked its work directory 3-4 times; it now does one pass (`_scan_work_dir`).
* `_ffmpeg_args()` rebuilt four encoder tables on every call; they are module constants.

## 6. Bugs fixed on the way

1. **Thumbnails were never saved.** `Path.glob(stem + ".*")` treats the `[video-id]` in yt-dlp's file name as a character class.
2. **Playlist items received every item's subtitles.** Sidecars are named `<stem>.<lang>.<ext>` but were matched with `p.stem == source.stem`, which never matched, so the code fell back to "all subtitle files".
3. **Custom FFmpeg path ignored by yt-dlp.** It is now passed as `ffmpeg_location`, so merging separate video+audio streams works with a path chosen in Settings.
4. **PNG cover detection was dead code** (`b"\\x89PNG"` with an escaped backslash), so PNG covers were tagged as JPEG.
5. **Possible FFmpeg deadlock.** stderr was only read after stdout closed; a chatty FFmpeg could fill the pipe and hang. stderr is now drained in a thread.
6. **Slow cancel.** Cancellation was only checked when FFmpeg printed a progress line. A watcher thread now terminates FFmpeg within ~250 ms.
7. **Lost playlists.** `save_music_playlists()` wrote to disk, then the next `setSetting()` rewrote the whole settings file from a stale in-memory copy, silently dropping the new playlist. Settings are now saved through `_persist()`, and `update_settings()` does read-modify-write.
8. **Partial settings file on crash.** Settings and the library cache are written atomically (temp file + `os.replace`) under a lock.
9. **Work folder leaked on cancel** during the yt-dlp download phase.
10. **Playback queue was reordered / dropped** on library refresh (shuffle order lost, remote previews removed, index not updated). The queue now keeps its order and the current index.
11. **Console window flashes** when FFmpeg/ffprobe are spawned from a windowed Windows build (`CREATE_NO_WINDOW`).

## 7. De-duplication

Proxy and browser-cookie handling was copy-pasted into three modules. It now lives in `engine.network_options()`.

## Verification

* All modules compile (`python -m py_compile`).
* Engine: real FFmpeg conversion, cancel mid-encode (partial output removed), option validation, cached tool probing.
* Music: library cache cold/warm, concurrent search, playlist persistence.
* Bridge (Qt event loop, multimedia/widgets stubbed): 200 progress ticks produce one coalesced `queueChanged`; `statusJson()` returns immediately; "play all" waits for the async scan; a playlist survives a later `setSetting()`.
* Not run: the real QML window (the sandbox has no GL libraries) and live yt-dlp downloads.

## Not changed (deliberately)

* `ums/ui.py` (legacy Widgets fallback) and the QML layout: no measured problem, and the bridge changes already remove the main cause of UI churn.
* The download/convert queue remains sequential, as documented in the README.
