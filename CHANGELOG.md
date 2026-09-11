### v 2.8.0
#### Architecture

- Added `ytget_gui/_version.py` as the single source for app name, organization, repository, and version.
- Added `ytget_gui/app.py` for CLI parsing, Qt bootstrap, palette setup, icon discovery, application identity, and single-instance handling.
- Reduced `ytget_gui/main.py` and `ytget_gui/__main__.py` to compatibility entry points into the new bootstrap.
- Added `ytget_gui/queue/model.py` and `queue/controller.py`.
- Moved `QueueItem` out of `download_worker.py` into the queue model.
- Added `workers/base.py`, `workers/log_buffer.py`, and `workers/proc.py` as shared infrastructure.
- Added `formats.py`, `theme.py`, dialog helpers, UI switch, CLI-argument parsing, text helpers, and cross-platform open/reveal helpers.
- Removed duplicated queue, worker, style, dialog, and format-selection responsibilities from the main window and settings classes.

#### Queue model and controller

- Added typed statuses: Pending, Downloading, Completed, Error, and Cancelled.
- Added persistent fields for stage, uploader, duration, queue attempts, last error, add time, output path, and output count.
- Added O(1) URL lookup, identity-safe indexing, deterministic sorting, block moves, visual reorder, retry reset, and completed-item clearing.
- Added atomic `queue.json` persistence with `fsync` and `os.replace`.
- Added recovery of interrupted jobs and legacy statuses.
- Added separate controller signals for item changes, structural changes, overall progress, run state, logging, and completion.
- Added explicit pause, skip, stop, retry, cancellation, shutdown, and finish-once semantics.

#### Download worker

- Replaced direct worker `run()` orchestration with timer-driven startup and shared base-worker behavior.
- Added a machine-readable progress sentinel and parser.
- Added playlist-entry and multi-stream progress weighting.
- Added structured output-file discovery and extension-change fallback.
- Added domain-aware referers and HLS preference controls.
- Added explicit groups for selection, output, runtime, network, subtitle, thumbnail, audio, video, and post-processing flags.
- Added interruptible browser-cookie refresh.
- Added delayed transient retries with cancellation polling.
- Fixed an uninitialized flat-playlist directory path affecting YouTube Music mixes/radios.
- Added playlist track-number writing and candidate renaming paths.

#### SpotDL worker

- Migrated to shared base-worker, process, environment, cancellation, log, and progress behavior.
- Improved process output parsing and cleanup.
- Normalized executable discovery and settings snapshots.

#### Metadata, titles, and thumbnails

- Added a structured `FetchResult` and cancellable fetch flow.
- Improved best-thumbnail ranking and condensed user-facing fetch errors.
- Metadata failure is non-fatal: the queued item remains downloadable.
- Added explicit cancellation of title and thumbnail fetches when queue items are removed.
- Reworked title-queue draining and process registration.
- Added cache-safe filenames, canonical YouTube watch URLs, AVIF support, and multiple thumbnail fallback paths.

#### Settings

- Replaced scattered serialization with declared plain/path key lists and validator maps.
- Added schema/version metadata to saved configuration.
- Added atomic writes and corrupt-file quarantine.
- Added helper binary discovery through environment, PATH, and bundled locations.
- Added safe defaults and normalization for paths, retries, formats, browsers, proxy, archive, HLS, and SpotDL.
- Extracted format construction from settings.

#### UI and styling

- Rebuilt main-window layout and menus.
- Reworked queue cards to update from `QueueItem`, show richer metadata/stage/progress, and expose output actions.
- Added responsive dialog layout, shared cards/dividers/forms, and centralized QSS.
- Added `Palette`, DPI scaling, typography helpers, and reusable component styles.
- Rebuilt Preferences, Advanced Options, About, and Update Manager on shared UI primitives.

#### Utilities and security

- Added safe non-shell CLI argument splitting and blocked app-owned yt-dlp flags that could conflict with worker control.
- Added cross-platform process-tree termination and hidden-console handling.
- Added safe path resolution, writable-directory checks, filename sanitization, and platform labels.
- Hardened URL and proxy validation.
- Hardened cookies as credentials with pruning, atomic writes, and restrictive permissions.
- Hardened updater downloads and Deno archive extraction.

#### Packaging and automation

- Bumped application metadata in `pyproject.toml`, `Info.plist`, and `version_info.txt` to 2.8.0.
- Added the new `queue` package to setuptools package data.
- Added a Windows debug PyInstaller workflow.
- Removed the Nuitka workflow.
- Removed the old test workflow.
- Removed the bundled Windows Inno Setup installer directory and dependency-download PowerShell script.
- Updated the PyPI workflow file minimally.
- Source comparison totals: **53 changed paths**, **11,189 insertions**, and **11,486 deletions**.

### v 2.7.8
- Queue progress bar no longer stuck at 0% during downloads. The worker's
  progress updates (e.g. "45% ETA 00:12") were being misread as a status
  label instead of a percentage, so the progress bar was never actually
  updated. Progress now updates live as each download proceeds.
- Fixed a bug where a failed download (e.g. yt-dlp exiting with an error)
  would restart from the beginning instead of moving on. The queue only
  advanced past an item on success, so on failure the same item — including
  full playlists — was picked back up and re-downloaded from scratch,
  looping repeatedly until stopped manually. The queue now always advances
  after a download finishes, whether it succeeded or failed.
### v 2.7.7 **Glassmorphism UI Update**
- This release introduces a massive visual overhaul of the entire application, transitioning from the opaque "Obsidian Steel" theme to a vibrant Glassmorphism design language. 
### v 2.7.6 **Custom CA certificate support**
- Custom CA certificate support for local MITM/domain-fronting proxies (e.g. MITM-DomainFronting). A new Custom CA certificate field in Preferences → Network lets you point at a self-signed cert (e.g. mycert.crt) so TLS validation keeps working against that specific certificate instead of being disabled outright.
### v 2.7.3 **Opus Audio, SpotDL Reliability & UI Refinements**
- **🎧 Opus audio support**
  - Added `audio_opus` format code for single-track Opus downloads (`--audio-format opus`).
  - Added `playlist_opus` format code for downloading playlists as Opus.
  - New settings presets: 🎧 Single Audio (Opus) and 🎶 Audio Playlist (Opus – YouTube/Music).
  - `.opus` added to the recognized audio file extensions used during post-processing.
- **Playlist/format code cleanup**
  - Merged the `youtube_music` format code into `playlist_mp3`; the optional artist/title metadata-parsing step (`YT_MUSIC_METADATA`) now applies to any playlist audio download (MP3 or Opus) instead of being tied to a specific format code.
  - Consolidated the 🎶 Audio Playlist (MP3 – YouTube) and 🎶 Audio Playlist (MP3 – YouTube Music) presets into a single 🎶 Audio Playlist (MP3 – YouTube/Music) preset.
  - `_is_audio_download()` now recognizes `audio_opus` and `playlist_opus`; playlist detection now checks for `playlist_mp3`/`playlist_opus` instead of `playlist_mp3`/`youtube_music`.
- **SpotDL reliability improvements**
  - `SPOTDL_THREADS` default raised from 6 to 12 to match known-good throughput.
  - `SPOTDL_AUDIO_PROVIDERS` default changed to `["youtube-music", "youtube"]`, adding an automatic fallback so a single provider hiccup doesn't cause a track to silently fail with no audio source.
  - Fixed false "success" reporting: spotdl exits 0 even when individual tracks fail. SpotDL runs now scan output for per-track failure markers and report "⚠️ finished, but N track(s) had errors" when applicable.
  - Removed a dead, unused `ffmpeg_dir` variable from the SpotDL command builder.
- **🎨 Dark theme lightened**
  - Surfaces across the app now read as rich dark grey/blue rather than near-black, updated consistently across `main_window.py`, `styles.py`, and `main.py`.
  - Accent colors and text greys were left unchanged.
- **Update Manager & About dialog cleanup**
  - Removed FFmpeg/FFprobe from the Update Manager; it's no longer checked, downloaded, or auto-installed.
  - Fixed a console window briefly flashing open when checking for updates on Windows.
  - Removed the "System" and "Dependencies" tabs and the "Check for Updates" button from the About dialog, which is now streamlined to just "About" and "License".
- **Fixed YouTube Music track numbering**
  - Track numbers were incorrectly tagged with a fixed/bogus value instead of actual playlist position. Now explicitly mapped from yt-dlp's `playlist_index` via `--parse-metadata`.

### v 2.7.0 **Spotify Support via SpotDL**
- Added full Spotify track and playlist downloading support using spotDL
- Seamlessly downloads Spotify content by resolving tracks through YouTube audio sources.
- **🔒 Optional SSL Certificate Bypass**
- Added new setting: Preferences → Network → Ignore SSL certificate errors (unsafe)
- When enabled, YTGet launches yt-dlp with: --no-check-certificates
- Useful for restrictive networks, broken proxy chains, DPI filtering, or misconfigured TLS environments.
- Disabled by default for security reasons.
- **🎨 Completely Redesigned Main UI**
- Introduced a refreshed and more modern interface across the application.
- Improved visual hierarchy, spacing, responsiveness, and queue readability.
- **🚀 New Cross-Platform Update Manager**
- Rebuilt the update system from scratch with full cross-platform support.
- The new update manager can independently update: yt-dlp, ffmpeg, deno and SpotDL

### v 2.6.1 **Dependency Updates**
- **Updated runtimes**: Deno upgraded to v2.8.1 and yt-dlp upgraded to 2026.03.17.

### v 2.6.0 **Thumbnail Reliability, UI Polish & Performance**
- **Fixed thumbnail fetching**
  - Thumbnails are now correctly fetched and displayed for YouTube videos and playlists.
  - Implemented **canonical URL normalization** for metadata and thumbnail extraction.
    - URLs containing `v=<video_id>` are converted to  
      `https://www.youtube.com/watch?v=<video_id>`
    - Prevents yt-dlp from misinterpreting playlist parameters such as  
      `&list=...` and `&start_radio=1`.
  - Greatly improves reliability for mixed playlist/watch URLs.

- **yt-dlp metadata pipeline improvements**
  - Metadata extraction and thumbnail writing now both use the canonicalized URL.
  - Cleaner error handling and reduced log noise.

- **UI improvement – automatic URL elision in QueueCard**
  - Long URLs are middle-elided using `QFontMetrics.elidedText`.
  - Prevents horizontal scrollbars and layout breakage.
  - Full URLs are preserved in a tooltip for easy copying.

- **Stability fix – prevent crash caused by invalid UTF-8 output**
  - Fixed crashes caused by malformed UTF-8 bytes in `yt-dlp` output.
  - Replaced all `subprocess.run(..., text=True, encoding="utf-8")` calls with binary mode (`text=False`) to avoid premature decoding in Python’s reader thread.

- **Performance – log buffering & throttling**
  - Implemented high-performance log buffering in `DownloadWorker` to prevent UI freezes during high-frequency output.
  - Added configurable throttles:
    - `_log_flush_ms` (default: 300 ms)
    - `status_throttle_ms` (default: 500 ms)
  - Introduced safety caps (`_max_entries_per_flush`, `_max_emit_bytes`) to keep the log window responsive during massive output bursts.
    
- **Prefer HTTP Live Streaming (HLS)**: Prefer HLS/m3u8 streams on configured domains to avoid 404s.

### v 2.5.3.0 **Dependency Updates**
- **Updated runtimes**: Deno upgraded to v2.6.8 and yt-dlp upgraded to 2026.02.04.

### v 2.5.2.0 **Deno JavaScript Runtime Integration**  
- **Automatic Deno detection**: the app now detects a bundled or configured `deno` binary and exposes its availability in the startup console.  
- **yt-dlp uses local Deno**: when present, `yt-dlp` is invoked with `--js-runtimes deno:/path/to/deno` so JS‑based extractors run against the local Deno runtime.  
- **Process PATH injection**: the Deno parent directory is added to the child process `PATH` (same approach as PhantomJS) so subprocesses can locate Deno reliably.

### v 2.5.1.3 - Persisted cookie settings and worker sync
* Persist cookie-related preferences immediately when changed in the Preferences dialog.
* Record a timestamped “last imported” cookie marker when cookies are exported from a browser.
* Ensure all worker modules that may refresh cookies (download, title-fetch, metadata) update AppSettings and persist the new cookie info as a best-effort operation.

### v 2.5.1.2 - Dynamic cookies, safer exports, and automatic refresh
* Added a secure cookie management flow that imports browser cookies, prunes them to avoid oversized headers, and optionally refreshes them automatically before metadata fetches and downloads.
* Integrated cookie refresh into title/metadata fetch workers and the download worker so authenticated downloads are more reliable without repeated manual exports.
* Fixed HTTP 413 failures caused by huge exported cookie dumps and improved UX around importing, persisting, and clearing cookies.

### v 2.5.1.1 - Console Log Limit and Performance Improvements
* Added a hard limit to the in-memory console log so the app keeps at most 200 log lines.
* Reduced UI work when appending logs by appending the newest entry directly when console filter is "All".
* Trimmed oldest entries automatically to prevent unbounded memory growth and excessive QTextEdit re-renders.
