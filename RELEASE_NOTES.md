# ✨ What's New v2.8.0

## Release summary

YTGet 2.8.0 is a major internal refactor focused on queue reliability, smoother downloads, safer persistence, clearer diagnostics, and a more consistent interface. The queue is now split into a dedicated model and controller, workers share common process and cancellation infrastructure, download progress is parsed from machine-readable yt-dlp output, and completed downloads can be opened directly from their queue cards.

The release also centralizes version metadata, improves format selection and HLS behavior, hardens cookie and update handling, adds a command-line diagnostics mode, and restructures Preferences, About, Update Manager, themes, and reusable UI components.

---

## ⚡ Highlights

### A more reliable queue

- Rebuilt the download queue around a dedicated `QueueModel` and `QueueController`.
- Queue changes are saved atomically, reducing the risk of losing the queue if the app or computer stops during a write.
- Interrupted `Downloading` items return as `Pending` after restart instead of remaining stuck.
- Legacy or unknown queue statuses are recovered as runnable items instead of being dropped.
- Stopped and skipped items remain visible as `Cancelled` and are not immediately scheduled again.
- Pressing **Start** explicitly re-arms previously cancelled items.
- Failed downloads can be moved to the end of the queue and retried later; after the configured retry limit, they remain visible as errors.
- The active download stays pinned while sorting or moving other items.
- Queue order remains safe while filtering; hidden items are not accidentally discarded.
- Duplicate URLs are rejected through a direct URL index.
- Queue lookup is now constant-time, improving responsiveness on large queues.
- Queue progress includes the current item’s fractional progress rather than only counting completed items.
- Import/export is available from **File → Save Queue As…** and **Load Queue…**.

### Better download progress and output tracking

- Replaced fragile scraping of yt-dlp’s human-readable progress bar with an explicit machine-readable progress template.
- Added continuous playlist progress instead of restarting the visible percentage for every track.
- Added weighted progress for downloads that use separate video and audio streams.
- Progress-stage text is now separated from item status, preventing corrupted status chips and stuck progress bars.
- Duplicate progress emissions are ignored.
- Worker logs are buffered, bounded, coalesced, and delivered in batches to reduce UI stutter.
- Subprocess output is read in larger chunks, reducing cross-thread event overhead.
- Final output paths are captured across download, merge, conversion, move, and already-downloaded messages.
- Queue cards record the final file or playlist folder and output count.
- Completed items now offer **Play file**, **Show in folder**, and **Copy file path** actions.
- Missing or moved output files are detected rather than treated as playable.

### Safer retries and cancellation

- Centralized worker lifecycle and cancellation behavior in a shared base worker.
- Added shared subprocess helpers for spawning, decoding output, constructing tool environments, and terminating process trees.
- Cancellation works while a retry delay is active.
- Worker thread teardown is bounded during application shutdown.
- The next worker starts only after the previous thread has unwound, preventing overlapping workers.
- Queue completion is announced once, avoiding duplicate post-queue actions such as shutdown.
- Retry detection covers temporary HTTP failures, rate limits, timeouts, connection failures, and unavailable formats.
- In-process retries and later queue requeues are now separate policies.

### Improved format selection

- Moved format-selector generation into a dedicated, testable `formats.py` module.
- Added explicit YouTube and universal presets from 480p through 8K.
- Universal presets include both height and width limits.
- Video selection now prefers AV1, then VP9, then other DASH/HTTP formats before HLS and pre-muxed fallbacks.
- Corrected codec matching for real yt-dlp codec identifiers such as `av01…` and `vp09…`.
- Added guaranteed `best` fallbacks to reduce “Requested format is not available” failures.
- Added safer audio fallback behavior.
- HLS preference is opt-in and domain-aware.
- YouTube domains are excluded from forced HLS preference so higher-quality DASH streams remain available.
- Added centralized detection for audio, playlist-audio, and Spotify pseudo-formats.

### Spotify and SpotDL improvements

- Spotify URLs are accepted directly in the main URL field.
- Spotify jobs are routed through the queue controller to `SpotDLWorker`.
- SpotDL settings are normalized through a dataclass rather than a duplicated manual mapping.
- Preferences support SpotDL output format, thread count, output template, lyrics, LRC generation, provider order, bitrate, yt-dlp arguments, FFmpeg arguments, overwrite policy, playlist numbering, explicit-content handling, SponsorBlock, unavailable tracks, and proxy behavior.
- Provider ordering is preserved with an ordered multi-select control.
- The Update Manager can detect and update SpotDL where supported.
- `spotdl` was added to project dependencies, although the supplied TOML syntax must be fixed before packaging.

### Cookies, proxies, and network behavior

- Browser-cookie export was rewritten with aggressive YouTube-focused pruning to avoid oversized request headers.
- Important cookies are prioritized before count and byte limits are applied.
- Cookie files are written atomically.
- Cookie files are restricted to owner read/write permissions where supported.
- Automatic browser-cookie refresh can run before downloads.
- The last successful cookie import time is recorded.
- Cookie refresh can be interrupted during cancellation.
- URL classification is host-based rather than substring-based, preventing YouTube-specific behavior from being applied to unrelated hosts containing `youtube.com` in a query string.
- Proxy validation now supports HTTP, HTTPS, SOCKS4, SOCKS5, and SOCKS5H.
- Update checks and downloads now respect the configured proxy and SSL/CA settings.
- A custom CA certificate takes precedence over disabling SSL verification.

### New diagnostics and support tools

- Added `ytget --doctor` for offline dependency and storage checks without opening the GUI.
- Doctor mode reports the app, Python, operating system, architecture, required Python packages, writable profile/download folders, and helper binaries.
- Missing required tools return a non-zero exit code.
- Added `--verbose` / `-v` startup logging.
- URLs can be passed on the command line and queued at launch.
- `--version` now reads from centralized version metadata.
- The About dialog now has **About**, **Environment**, and **Licence** tabs.
- Added **Copy diagnostics** for bug reports.
- Startup logging reports resolved paths for yt-dlp, FFmpeg, FFprobe, Deno, and SpotDL, plus active proxy/archive/SponsorBlock/naming options.

### Interface and usability updates

- Reworked the main window as a view over the queue controller instead of mixing UI, scheduling, and worker ownership.
- Added a clearer empty-queue state and drag-and-drop feedback.
- Added queue search and sorting by **Added**, **Title**, or **Status**.
- Added bulk selection actions and a selected-item count.
- Added output-log level filtering, copy, and clear controls.
- Added menu actions for queue import/export, opening the download folder, choosing cookies, preferences, updates, About, and post-queue behavior.
- Added accessible names to key controls.
- Added a reusable animated switch control.
- Added shared dialog components and a centralized dark theme/palette.
- Added DPI-aware sizing and global font helpers.
- Repaired mojibake-prone text and bullet rendering.
- Added cross-platform open/reveal helpers for downloaded files and folders.
- Window geometry is stored through Qt settings.

### Preferences overhaul

- Reorganized Preferences into focused pages for network, cookies, SponsorBlock, subtitles, playlists, output naming, processing, thumbnails, and SpotDL.
- Added declarative widget bindings and centralized load/save/reset behavior.
- Added live validation and first-error focus.
- Added filename-template previews and a field reference for title, extension, duration, resolution, artist, uploader, channel, album, track number, playlist title/index, ID, upload date, release year, and sequence number.
- Added validation for clip times, playlist selections, rate limits, dates, subtitle language expressions, and proxies.
- Advanced Options is now focused on clip extraction and one-run playlist selection.

### Settings and storage hardening

- Configuration writes are atomic and synced before replacement.
- Corrupt configuration files are quarantined as `.json.corrupt` rather than silently destroying defaults or repeatedly failing.
- Persisted settings are sanitized and coerced through per-key validators.
- Numeric retry values are bounded.
- Invalid containers, thumbnail formats, filename modes, browser names, SponsorBlock values, and HLS domains are normalized.
- Saved helper-tool paths are restored only if they still exist; otherwise normal discovery resumes.
- Helper binaries can be resolved from environment overrides, `PATH`, or bundled files.
- Download-directory changes now refresh output templates and create the target directory.
- Empty cookie/archive values no longer collapse to the current directory.
- Download archive arguments are only emitted when the archive path is usable.
- Thumbnail cache and application-data paths are centralized.

### Thumbnail and cover-art handling

- Reworked thumbnail retrieval with cache validation, URL canonicalization, YouTube thumbnail probing, requests/yt-dlp fallbacks, and AVIF conversion.
- Added cancellable thumbnail subprocess handling.
- Thumbnail logging can be enabled separately.
- Reworked square audio-cover processing for ID3/MP3, FLAC, MP4/M4A, and Ogg/Opus containers.
- Cover-cropping work is cancellable and better isolated from the main window.

### Updates and installer safety

- Rebuilt the Update Manager around a common tool model.
- Missing or unknown installations are no longer incorrectly labeled up to date.
- Added per-tool status, progress, cancellation, and clearer platform information.
- YTGet self-update opens the release page; helper tools can be installed in place.
- Downloads use bounded timeouts and configured proxy/SSL behavior.
- Binary replacement is staged and atomic.
- Deno archive extraction rejects absolute paths and directory traversal and enforces a size limit.
- Installed helper binaries receive executable permissions where needed.


---
## 🆚 Updated Dependencies
- **yt-dlp:** `2026.08.19`
- **ffmpeg:** `9.0.1`  
- **deno:**  `2.9.6`
- **SpotDL (Windows only):**  `4.5.2 - hotfix`
---
### 📥 Official Downloads
<table align="center">
  <thead>
    <tr>
      <th>Operating System</th>
      <th>Architecture</th>
      <th>Format</th>
      <th>File Size</th>
      <th>Download</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="2">🪟 <strong>Windows</strong></td>
      <td rowspan="2"><code>x86_64</code></td>
      <td>ZIP</td>
      <td><strong>255 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-windows.zip">
          <img src="https://img.shields.io/badge/Download-ZIP-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows ZIP Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>165</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-windows.7z">
          <img src="https://img.shields.io/badge/Download-7z-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows 7z Download">
        </a>
      </td>
    </tr>
    <tr>
      <td rowspan="2">🐧 <strong>Linux</strong></td>
      <td rowspan="2"><code>x86_64</code></td>
      <td>tar.gz</td>
      <td><strong>255 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-linux.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>190</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-linux.7z">
          <img src="https://img.shields.io/badge/Download-7z-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux 7z Download">
        </a>
      </td>
    </tr>
    <tr>
      <td rowspan="2">🍎 <strong>macOS</strong> (Apple Silicon)</td>
      <td rowspan="2"><code>arm64</code></td>
      <td>tar.gz</td>
      <td><strong>155 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-macOS-arm64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>105</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-macOS-arm64.7z">
          <img src="https://img.shields.io/badge/Download-7z-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM 7z Download">
        </a>
      </td>
    </tr>
    <tr>
      <td rowspan="2">🍎 <strong>macOS</strong> (Intel)</td>
      <td rowspan="2"><code>x86_64</code></td>
      <td>tar.gz</td>
      <td><strong>155 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-macOS-x86_64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>110</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-macOS-x86_64.7z">
          <img src="https://img.shields.io/badge/Download-7z-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel 7z Download">
        </a>
      </td>
    </tr>
  </tbody>
</table>

---

### 📊 VirusTotal Scan
🔗 [View scan results on VirusTotal](https://www.virustotal.com)  
_The archive contains `.exe` files, which may still occasionally be flagged by some antivirus engines as **false positives**. These are not actual threats._
