### v 2.7.2 **Opus Audio, SpotDL Reliability & UI Refinements**
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
