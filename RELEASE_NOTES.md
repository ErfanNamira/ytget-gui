## ✨ What’s New

🖼️ **Reliable video thumbnails**  
- Video thumbnails are now **correctly fetched and displayed** for YouTube videos and playlists.
- Implemented **canonical URL normalization** before metadata and thumbnail extraction.
  - URLs containing `v=<video_id>` are converted to  
    `https://www.youtube.com/watch?v=<video_id>`
  - Prevents `yt-dlp` from misinterpreting playlist parameters such as  
    `&list=...` and `&start_radio=1`.
- Greatly improves reliability for mixed playlist/watch URLs.

🧼 **Cleaner Queue UI**
- **Automatic URL elision** in `QueueCard` prevents long URLs from breaking layout.
- URLs are middle-elided using `QFontMetrics.elidedText`.

---

## ✅ Fixes & Improvements

- **Thumbnail fetch stability**
  - Metadata extraction and thumbnail writing now both use the canonicalized URL.
  - Reduced error noise and clearer failure paths in logs.

- **Crash fix – invalid UTF-8 in yt-dlp output**
  - Prevented crashes caused by malformed UTF-8 bytes.
  - Replaced all `subprocess.run(..., text=True, encoding="utf-8")` calls with binary mode (`text=False`) to avoid premature decoding in Python’s reader thread.

- **Performance – log buffering & throttling**
  - Added high-performance log buffering in `DownloadWorker` to prevent UI freezes during heavy output.
  - Introduced throttles:
    - `_log_flush_ms` (default: 300 ms)
    - `status_throttle_ms` (default: 500 ms)
  - Safety caps (`_max_entries_per_flush`, `_max_emit_bytes`) ensure the log window stays responsive during output bursts.

---

## 🆚 Updated Dependencies

- **yt-dlp:** `2026.02.04`
- **ffmpeg:** `8.0.1`  
- **deno:**  `2.6.8`

---

## 📥 Downloads

#### 🪟 Windows · x86_64 · 212 MB  
[⬇ Download for Windows](https://github.com/ErfanNamira/ytget-gui/releases/download/2.6.0/YTGet-windows.zip)

#### 🐧 Linux · x86_64 · 255 MB  
[⬇ Download for Linux](https://github.com/ErfanNamira/ytget-gui/releases/download/2.6.0/YTGet-linux.tar.gz)

#### 🍎 macOS (ARM) · arm64 · 155 MB  
[⬇ Download for macOS ARM](https://github.com/ErfanNamira/ytget-gui/releases/download/2.6.0/YTGet-macOS-arm64.tar.gz)

#### 🍎 macOS (Intel) · x86_64 · 158 MB  
[⬇ Download for macOS Intel](https://github.com/ErfanNamira/ytget-gui/releases/download/2.6.0/YTGet-macOS-x86_64.tar.gz)

---


### 📊 VirusTotal Scan
🔗 [View scan results on VirusTotal](https://www.virustotal.com)  

_The archive contains `.exe` files, which may still occasionally be flagged by some antivirus engines as **false positives**. These are not actual threats._  
