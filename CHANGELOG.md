### v 2.8.0

System tray, clipboard watcher, scheduler, run-at-login, plain-text link
import/export, a Windows installer, per-item advanced options, several
formats of one link in the queue, download-size estimates, an unlisted-site
policy, and a faster cold start.

#### Windows installer

- Added `packaging/windows/ytget.iss`, an Inno Setup 6 script that builds
  `YTGet-<version>-windows-setup.exe`.
- Installs per user (`PrivilegesRequired=lowest`), so no UAC prompt is needed,
  with optional desktop and run-at-login shortcuts and a proper uninstaller.
- The release workflow now builds, verifies and checksums the installer
  alongside the existing ZIP and 7z assets. The debug workflow builds it too,
  so it can be tested before tagging.

#### Queue

- The same link can now be queued in several formats at once. Queue identity
  moved from the URL to url+format, so 1080p and MP3 of one video are two
  independent rows; only an identical url+format pair is refused as a
  duplicate.
- Metadata and thumbnails are still fetched once per URL and fanned out to
  every format of it. A newly added format immediately inherits the title and
  thumbnail a sibling row already has.
- Removing one format keeps the other row's thumbnail and in-flight metadata
  fetch alive; the cached image is only deleted when no row for that URL is
  left.
- Each card now shows the estimated download size next to the format, for
  example `YouTube 1440p QHD  ·  ~1.24 GiB`. The estimate reuses the metadata
  JSON that is already fetched, so no extra yt-dlp call is made: the largest
  stream for the selected height plus the best audio-only stream, or audio
  alone for audio presets. Sites that only publish progressive streams are not
  double-counted, and a bitrate x duration fallback is used when no size is
  advertised. Playlists show no size.
- Duration and uploader are now shown on the card. Both were parsed and then
  dropped, because the metadata signal had no room for them.
- The format label is now part of the row search text.
- Added `ytget_gui/naming.py`. A second format of the same URL keeps the
  default `%(title)s.%(ext)s` naming unless it would land on the same
  container as an item already queued for that URL; in that case the
  quality tag is appended, e.g. `Title QHD.mkv` next to `Title.mkv`.
  Different containers (`.mkv` and `.mp3`) cannot collide, so neither is
  renamed. Tags come from the format label, with a numeric suffix as the
  last resort, so no two rows can target one path.
- The download archive is skipped for such an item. The URL is already
  recorded from the first format, so with `ENABLE_ARCHIVE` on yt-dlp would
  otherwise refuse the second quality as "already recorded".
- Queue cards now carry the queue key rather than the URL, so removing,
  opening, retrying or revealing the second format of a URL no longer acts
  on the first one.

#### Advanced options are per item

- Clip start/end, playlist item selection and reverse order now apply only to
  the items added while they are set, instead of being written to the shared
  settings and silently applying to every item in the queue.
- Pending overrides are stamped onto each queue item as it is added and applied
  to that item's settings snapshot at download time.
- The Advanced button shows a dot and a tooltip listing what is armed.
- Persisted overrides are whitelisted and type-checked on load, so a
  hand-edited `queue.json` cannot inject arbitrary settings.

#### Unlisted sites

- Replaced the "only known sites" switch with an explicit policy in
  **Preferences → Watcher**: queue unlisted sites automatically (the default),
  ask first, or ignore them.
- On "ask", the watcher reports the hosts involved and nothing is queued until
  it is confirmed.
- The old boolean is still honoured on upgrade: `true` becomes "ignore".

#### Performance

- Faster cold start: the Preferences, About, Update Manager and Advanced
  dialogs and the cover-crop worker are no longer imported before the first
  paint, and the clipboard watcher, scheduler, tray setup and the environment
  probe (which shells out to yt-dlp and ffmpeg) now run on the first idle tick
  instead of inside the window constructor.
- The queue list is patched in place on add and remove instead of destroying
  and re-creating every card on each queue change.
- Row lookups use an index instead of a linear scan on every progress tick and
  thumbnail callback.
- Search text is memoised per row, so filtering a long queue is no longer
  quadratic in keystrokes.

#### Album art

- Covers are now cropped to 1:1 as each item finishes downloading instead
  of in one pass at the end of the queue. Stopping the queue no longer
  leaves already-downloaded audio uncropped.
- Only the files that item produced are opened, rather than rescanning the
  whole downloads folder on every run.
- Items finishing while a pass is still running are queued behind it, so
  two threads can never rewrite the same tags at once. A pending power
  action still waits for cropping to finish.

#### Fixed

- The size estimate never appeared: `main_window` called
  `formats.estimate_download_size()` without importing `formats`, so every
  metadata callback raised `NameError` before the size was stored. The
  metadata signal payload was also built through an unimported helper in
  `title_fetch_manager`.
- Items restored from a queue saved by an older build carry no size. The
  unfinished ones now get a background details refresh at start-up, so
  sizes appear for an existing queue instead of only for new additions.
- Installer: the exe was listed twice in `[Files]`; an upgrade kept the
  previous build's `_internal` tree, which can crash the app with mixed Qt
  DLLs; an uninstall left YTGet's own run-at-login registry value behind;
  and `x64compatible` is now guarded for Inno Setup below 6.3. Uninstall
  also offers to delete the per-user profile in `%LOCALAPPDATA%\YTGet`.
- The release workflow excluded the versioned installer from the uploaded
  assets while the notes linked to exactly that filename, so the installer
  download 404'd.
- **Show in folder** did nothing on Windows. Explorer was launched with a
  hidden-window flag and with `/select,` quoted as a separate argument, which
  Explorer rejects. It is now invoked correctly, and the hidden-window flag was
  also removed from the `open`/`xdg-open` fallbacks.
- Removing an item from the queue left its thumbnail on screen. `takeItem()`
  dropped the list row but left the card widget, and its pixmap, parented to
  the viewport. Rows now free their widget, and the cached image file is
  purged.
- A metadata fetch that finished after its item was removed could re-create the
  deleted card. Pending fetches are now cancelled on removal.
- `utils.text.short()` could return a string longer than the requested limit.
- Open-ended playlist ranges such as `5:` and `:3` were rejected as invalid.

#### System tray

- Added `ytget_gui/tray.py`: a tray icon built from the app `icon.ico`, with a
  graceful no-op fallback when the desktop session has no tray host.
- Tray menu: live status line, show/hide window, start, pause, skip, stop,
  "When the queue finishes" submenu, clipboard watcher toggle, queue clipboard
  now, clear finished, open download folder, Preferences, and Exit.
- Added a dynamic tooltip and optional balloon notifications for queue,
  watcher, and scheduler events.
- Added minimise-to-tray and close-to-tray options. Only the tray Exit action
  (or a real quit) bypasses close-to-tray.
- Left/double/middle-clicking the tray icon toggles the window.
- Added a Tray page in Preferences for all of the above.
- The post-queue power action is now persisted in the config instead of
  resetting to Keep on every launch.

#### Clipboard watcher

- Added `ytget_gui/watcher.py`: captures supported links from the clipboard and
  queues them automatically.
- Added `ytget_gui/sites.py` with 76 recognised yt-dlp-supported sites and
  host-suffix matching, so a URL that merely mentions `youtube.com` in a query
  string is never misclassified.
- Added a Watcher page in Preferences: enable/disable, poll interval,
  auto-start the queue, notifications, per-category default formats (YouTube,
  YouTube Music, Spotify, everything else), skip playlists, ignore duplicates,
  and a checkable site allowlist with select all/none.
- Added Tools menu entries: "Clipboard Watcher" (Ctrl+Shift+V) and "Queue
  Clipboard Now" for a one-shot capture.
- `enqueue_urls` accepts an optional format label, so watcher additions can use
  a per-site preset while manual additions keep using the main window format
  box.
- Captures are de-duplicated against queue history and capped at 25 links per
  clipboard change. Both `dataChanged` and a poll timer are used, because the
  signal alone is unreliable on Windows and X11.

#### Scheduler and run at login

- Added `ytget_gui/scheduler.py` and a Scheduler page in Preferences.
- Start the queue and stop the queue at set times, each independently
  toggleable.
- Runs daily, or only on chosen weekdays.
- Power manager: Shutdown, Sleep, Restart, or Close at a set time. This runs
  even when the queue has not finished; downloads are stopped first and any
  pending post-queue action is cleared so two power commands cannot race.
- Events fire at most once per calendar day, with a five-minute catch-up window
  so a briefly suspended machine still triggers. Events already in the past are
  seeded as fired at launch, so enabling the scheduler at noon does not
  immediately run that morning's stop.
- Added `ytget_gui/autostart.py` and a Run at login card: a startup entry via
  the Windows `HKCU` Run key, a macOS LaunchAgent, or a Linux XDG autostart
  `.desktop` file, with start-hidden-in-tray and a configurable delay
  (0-600 s, default 30 s). The active path is shown in Preferences, and
  failures are logged instead of blocking a Preferences save.
- Added `--minimized` and `--delay SECONDS` command line flags. The delay is
  applied before Qt starts, and `--minimized` hides to the tray, falling back
  to a minimised window when no tray host exists.

#### Link import and export

- Added `ytget_gui/dialogs/link_io.py`.
- **File > Import Links from Text File…** (Ctrl+I): one link per line, with a
  review dialog offering a per-link format, one format for all links via
  "Apply to all", per-line exclusion, select all/none, and a live selected
  count.
- Links already in the queue are listed but unticked and marked; in-file
  duplicates are collapsed; blank lines and `#`, `;`, `//` comments are
  ignored; bare lines such as `www.example.com/watch` get `https://`
  prepended; lines that are not links are counted and reported rather than
  silently dropped.
- The importer also reads `url | Format` and tab-separated form, so an exported
  file round-trips with its formats.
- **File > Export Links to Text File…** (Ctrl+E): export everything in the
  queue, the current selection, or only waiting/finished/failed items, each
  option showing its item count. Optionally writes the format after each link
  and a `#` comment header with the date and count. `.txt` is appended when the
  extension is omitted.

#### Settings

- Added tray, watcher, scheduler, and startup keys with validation, including
  clamped delays and intervals, weekday lists, and `HH:MM` time coercion that
  falls back to the default instead of raising on a hand-edited config.

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
