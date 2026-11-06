# Universal Media Studio

A local-first desktop GUI for **yt-dlp + FFmpeg**. It is designed for people who want a simple downloader for everyday use and a deeper encoding panel when they need it.

> This package is a desktop application, not a Firefox/LibreWolf extension. A browser extension would need to communicate with a locally installed application through Firefox Native Messaging; that integration is not included in this desktop build.

## Features included

### Downloader
- Analyze a URL before downloading and list the source formats yt-dlp exposes.
- Select best video + audio, best single file, audio-only, capped resolutions, or an individual available source format.
- Add one URL or a newline-separated batch of URLs to a persistent in-session queue.
- Download playlists when the source and yt-dlp adapter support them.
- Download subtitle tracks and automatic captions when available; optionally embed detected subtitle files during output processing.
- Optional thumbnail download.
- yt-dlp retry, fragment retry, fragment concurrency, and transfer continuation settings.
- Optional browser-cookie reuse for supported browsers (Brave, Firefox, Chrome/Chromium, Edge, Opera, Safari, Vivaldi) when a site requires an already-authenticated session.
- Automatic/system proxy, explicit HTTP(S) proxy, or direct connection modes.

### FFmpeg conversion and remuxing
- Convert local files or downloaded media to MP4, MKV, WebM, MOV, AVI, 3GP, TS, MPEG, OGV, M4V, MP3, M4A, AAC, Opus, OGG, FLAC, WAV, AIFF, and WMA, subject to the installed FFmpeg build. ALAC is available as an audio codec inside a compatible container such as M4A.
- Remux compatible streams without re-encoding by selecting `copy` codecs.
- Video codec choices: copy, H.264, HEVC, AV1, VP9, VP8, MPEG-4 Part 2, MPEG-2, and Theora.
- Audio codec choices: copy, AAC, MP3, Opus, Vorbis, FLAC, PCM, and ALAC.
- FPS conversion, common output-height presets, and custom width × height scaling.
- Video rate control: CRF, CBR, VBR, CQ-style bitrate mode, or source/copy behavior where applicable.
- Separate audio bitrate, sample rate, and mono/stereo channel options.
- Explicit encoder selection, including software encoders and optional NVENC / QSV / AMF hardware encoders where the installed FFmpeg build and drivers support them. Auto mode prefers software encoders and checks the local encoder list.
- Optional codec profile, level, pixel format (including common 10-bit formats), color space, and color range controls.
- Metadata and chapter mapping.
- Downloaded subtitle sidecars can be preserved; embedding is attempted when selected and supported by the source/container.
- Progress reporting, cancellation, non-empty output checks, and ffprobe stream validation when ffprobe is installed.

### Interface and queue
- Dark, minimal sidebar dashboard with Downloader, Converter, Queue, and Settings pages.
- Simple profile selection with expandable advanced controls.
- Sequential queue for downloads and conversions, cancellation, failed-task retry, queued-task reordering, removal, logs, and task history for the current session.
- Custom presets saved locally.
- Built-in profiles: Best Available Quality, Smallest File, Balanced Quality and Size, Mobile Compatible, Low-End Device, Social Media Share, Archive Quality, Audio Only, Lossless Audio, 3GP Legacy Mobile, MP4 Universal Compatibility, and Web Optimized.

## Requirements

- Windows 10/11, Linux, or macOS desktop.
- Python 3.10 or newer.
- yt-dlp with its default extras (installed by the launcher through `requirements.txt`), including YouTube JavaScript challenge support components.
- FFmpeg for merging separate audio/video streams, conversion, remuxing, codec controls, and subtitle embedding.
- ffprobe is recommended for output validation. It is commonly distributed with FFmpeg.

For current YouTube extraction, install a supported JavaScript runtime such as **Deno** and make sure it is on PATH. yt-dlp uses its EJS challenge solver when available; YouTube may otherwise return bot-check, signature, or missing-format errors. Update the app dependencies with `python -m pip install -U "yt-dlp[default]"` after an extractor change. A current yt-dlp build and JS runtime improve compatibility but cannot guarantee access when YouTube requires account verification, cookies, or blocks the network.

Connection settings can use the system proxy discovered by Python/OS proxy configuration, a manually entered HTTP(S) proxy URL, or direct mode. Browser-cookie access depends on the browser profile being unlocked and readable by the current user. The connection test checks reachability of YouTube; it does not guarantee that every media host is reachable.

The application does not bundle FFmpeg binaries. Install a trusted FFmpeg build yourself and make sure `ffmpeg` and `ffprobe` are available on PATH, or select their executable paths in **Settings**. The app does not silently download or execute native binaries.

## Install and run on Windows

1. Install Python 3.10+ from <https://www.python.org/downloads/> and enable **Add Python to PATH**.
2. Install FFmpeg from a trusted distribution and add its `bin` directory to PATH (or set the executable paths in the app).
3. Double-click `run_windows.bat`.
4. The first launch creates `.venv`, installs PySide6 and yt-dlp with its default extras, then opens the GUI. Later launches reuse that environment.

To create an optional Windows app folder with PyInstaller, run `build_windows_exe.bat`. FFmpeg and ffprobe remain separate system dependencies.

## Install and run on Linux / macOS

Install Python 3.10+, FFmpeg, and (on many Linux distributions) the Qt runtime libraries, then run:

```bash
chmod +x run_linux.sh
./run_linux.sh
```

Or install manually:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

## Usage

1. Open **Downloader** and paste a URL. Click **Analyze** to inspect the formats yt-dlp can access.
2. Select a source quality and output format. The output format `Original` preserves the downloaded file without a container conversion.
3. Choose a preset or enable **Show advanced controls** to set codecs, FPS, resolution, rate control, CRF, bitrates, subtitles, and metadata handling.
4. Add the task to the queue. Open **Queue** to view progress, logs, cancellation, and retries.
5. Open **Converter** to choose local files and enqueue one or more FFmpeg conversions.
6. Configure output paths and tool executables in **Settings**.

### Rate-control notes
- CRF is not a universal quality scale: its useful range and meaning depend on the selected encoder.
- CBR and VBR require a video bitrate. Some codecs and containers have different rate-control capabilities.
- Setting a higher output resolution does not create real detail absent from the source.
- `copy` means no re-encoding. It can fail when the input codec is incompatible with the selected output container.
- Encoder availability varies by FFmpeg build. An installed FFmpeg may not contain every encoder listed in the interface. Hardware encoders can appear in the FFmpeg encoder list but still fail when the relevant GPU, vendor driver, or runtime library is unavailable.

## Known limitations

- This is a desktop GUI, not a browser-toolbar extension. It does not automatically inspect the currently open Firefox/LibreWolf tab.
- It does not bypass DRM, encryption, subscription controls, authentication barriers, geo restrictions, or website access controls. Some websites may block downloads or require supported authentication cookies configured through yt-dlp outside this UI.
- Website support and format availability are determined by yt-dlp and the site. No universal website support is promised.
- Queue tasks run sequentially. yt-dlp may use concurrent fragments for a single supported fragmented stream, but multiple separate queue tasks are not run simultaneously.
- Pause/resume controls are not exposed in this version. yt-dlp continuation is enabled where a server and transfer method support it.
- Two-pass encoding, exact target-file-size encoding, frame interpolation, automated hardware-encoder selection, and arbitrary FFmpeg argument entry are not exposed in this version.
- The subtitle embed option attempts to mux detected subtitle files; compatibility depends on subtitle format, selected container, and FFmpeg build. Separate subtitle downloads are preferred when embedding is unavailable.
- ffprobe validation is skipped with a warning when ffprobe is not installed.
- The `CQ` option currently uses bitrate-based quality targeting where supported by the selected encoder; it is not a universal encoder-independent CQ implementation.

## Privacy and safety

- URL inspection and media processing run locally through yt-dlp and FFmpeg.
- No analytics, telemetry, ad network, cloud conversion API, or third-party media proxy is included.
- Settings are stored in `~/.universal_media_studio/settings.json`.
- Downloaded media is saved only to the output folder you choose.
- Use the application only for media you own or are otherwise authorized to download.

## Project layout

```text
UniversalMediaStudio/
├── app.py
├── requirements.txt
├── run_windows.bat
├── run_linux.sh
├── build_windows_exe.bat
├── README.md
├── LICENSE
└── ums/
    ├── config.py
    ├── engine.py
    ├── presets.py
    ├── ui.py
    └── workers.py
```

## Troubleshooting

- **yt-dlp missing or YouTube formats unavailable:** run `python -m pip install -U "yt-dlp[default]"` in the project environment and install Deno (or another yt-dlp-supported JavaScript runtime) on PATH. Restart the app. For videos that require sign-in, configure supported browser cookies in yt-dlp; the app does not bypass access controls.
- **FFmpeg missing:** install FFmpeg, restart the app, and check Settings → Detected tools.
- **Separate streams fail to merge:** install FFmpeg and ensure `ffmpeg` is on PATH.
- **Encoder not found:** your FFmpeg build may not include that encoder; choose another codec or install a build with the required encoder.
- **MP3 attached-picture streams:** FFmpeg reports embedded album art as video streams (often PNG/JPEG). These are cover images, not playable video. UMS audio-only conversion maps only the audio stream, so the pictures are not exported as video. The Music downloader uses one cover source at a time to avoid duplicate APIC artwork frames.
- **Media Foundation `*_mf` messages:** `av1_mf`, `hevc_mf`, and `h264_mf` are FFmpeg's Windows Media Foundation encoder wrappers. UMS Auto mode does not select these wrappers; it prefers its configured software encoders and then supported NVENC/QSV/AMF encoders. A failed MFT probe alone does not mean a conversion failed—check the FFmpeg exit code and output validation. When a selected hardware encoder fails, choose a software encoder such as `libx264`, `libx265`, or `libsvtav1`.
- **Qt FFmpeg codec-dump messages during music playback:** Qt Multimedia can print its codec inventory on first decode when `QT_FFMPEG_DEBUG` and Qt FFmpeg logging are enabled. UMS removes an inherited `QT_FFMPEG_DEBUG` by default; set `UMS_KEEP_QT_FFMPEG_DEBUG=1` to opt in when collecting a diagnostic log. This does not change the external FFmpeg converter's error reporting. Do not disable all FFmpeg logging to hide these lines, because that can also hide real decoder errors.
- **Unsupported or protected URL:** try a source that provides accessible, non-DRM media and check the yt-dlp error in the Queue activity log.

## Development checks

Run the lightweight tests with:

```bash
python -m unittest discover -s tests -v
```

The project uses PySide6 (Qt for Python) for the GUI, yt-dlp for media extraction/downloads, and FFmpeg/ffprobe for local media processing.

## Native music workspace (Unstream-inspired)

The PySide6 desktop app includes a native music workspace for catalog discovery, local audio organization, playlists, and lyrics lookup. It does not require a separate browser app.

### Music discovery and tagged audio

- Search track metadata in Deezer and Apple Music catalogs.
- Search YouTube and SoundCloud through yt-dlp's supported search extractors.
- Look up available lyrics through LRCLIB.
- Paste a public Spotify track, album, or playlist URL. The app reads public Spotify embed metadata without a Spotify client ID, client secret, or user token, then searches YouTube with yt-dlp for each track and converts/tags the match with FFmpeg. No spotDL or Spotify API credentials are used. Spotify's embed structure is undocumented; playlists longer than 100 items are extended through an anonymous embed-player endpoint on a best-effort basis.
- Music matching uses yt-dlp with its default extras and an available JavaScript runtime for current YouTube challenge handling. FFmpeg is required for MP3 extraction, metadata tagging, and artwork embedding. Mutagen is used for reading local library tags and embedded cover art.

### Local library and playlists

- Scan the configured output directory for audio files and open them in the system's default player.
- Create local playlists that reference audio files on disk.
- Import and export M3U/M3U8 playlist files.
- Playlist definitions are stored alongside the existing local settings; media files are not moved or copied by playlist operations.

### Run

The desktop application now launches its native QML interface. The original Python media engine, queue workers, settings, and presets remain the backend. The QML interface includes animated navigation, music discovery, Spotify link resolution, downloads, a persistent local player, conversion controls, library, playlists, and settings. To start, use the existing launcher. Music search/download uses the yt-dlp dependency in `requirements.txt`; Mutagen is included there for local tags and embedded artwork. No spotDL install or Spotify developer credentials are needed.

Music catalog and lyrics search require an internet connection. Search results are metadata from the selected public providers; availability and source matching vary by provider and location. Use downloads only for media you are authorized to save.

This native implementation adapts Unstream-inspired music workflows to PySide6 rather than running Unstream's separate React/FastAPI application. Music sub-navigation uses a compact segmented switcher with animated fade transitions instead of visible nested tabs. The native UI now includes the searchable/sortable music library, artwork and tags, local playlists, and a persistent player with track navigation. Catalog search and lyrics use public providers; Spotify collection metadata is resolved from public embed pages, then each track is matched with yt-dlp.

## Native QML desktop interface

The desktop shell is implemented in **PySide6 + Qt Quick (QML)**. It uses the original Python media engine and background workers through `ums/qml_bridge.py`; no web server or browser runtime is required.

- Run with the existing Windows or Linux launcher.
- For local development, install `requirements.txt` and run `python app.py`.
- Build the Windows folder with `build_windows_exe.bat`; the script includes the QML directory as application data.
- The QML Settings page includes connection mode, proxy discovery/test, browser-cookie selection, and a project releases shortcut. The QML interface uses the same Inter typeface as Unstream (bundled under its SIL Open Font License) and now includes a searchable/sortable local library, embedded album artwork and tags, favorites, local playlists, and a persistent player with previous/play-pause/next, seek, and volume. The original full-featured Widgets UI remains available as a fallback with `python legacy_app.py` (Windows: `run_legacy_windows.bat`).

### Native QML music discovery and general media downloads

The native desktop UI includes a music-first Discover view with catalog filters for tracks, artists, albums, and playlists. Deezer's public catalog provides artist/album/playlist results; track search can combine Deezer, Apple Music previews, YouTube, and SoundCloud via yt-dlp. Track results can be previewed when a source preview exists, matched for download, or opened for lyrics.

The dedicated **Downloader** page accepts one or multiple URLs (one per line) from YouTube and other sites supported by yt-dlp, lets you analyze the first URL, choose a quality preset and output container, and queue tasks. Public Spotify track, album, and playlist URLs are resolved from public embed metadata without Spotify API credentials; the resulting track list is matched against YouTube via yt-dlp. Spotify metadata does not itself provide the audio stream.