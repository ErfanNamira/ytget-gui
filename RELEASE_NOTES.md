## ✨ What’s New

🍃 **Deno JavaScript Runtime Integration**  
- **Automatic Deno detection**: the app now detects a bundled or configured `deno` binary and exposes its availability in the startup console.  
- **yt-dlp uses local Deno**: when present, `yt-dlp` is invoked with `--js-runtimes deno:/path/to/deno` so JS‑based extractors run against the local Deno runtime.  
- **Process PATH injection**: the Deno parent directory is added to the child process `PATH` (same approach as PhantomJS) so subprocesses can locate Deno reliably.

---

## 🛠️ Build & CI Changes

🔁 **Latest Deno fetched at build time**  
- GitHub Actions workflow updated to query the Deno releases API and download the **latest** Deno release during CI.  
- The workflow selects the correct asset for each runner/arch, extracts the ZIP, and places the `deno`/`deno.exe` binary beside `ffmpeg`, `ffprobe`, `phantomjs`, and `yt-dlp`.

---

## ✅ Fixes & Improvements

- **Backward compatible**: if Deno is absent, app behavior is unchanged; `yt-dlp` falls back to its default JS runtime behavior.  
- **Cross‑platform support**: detection, packaging, and PATH injection implemented for Windows, macOS, and Linux.  
- **User guidance**: startup warnings include the official Deno installation docs to help users install a runtime when needed.  
- **Safe guards**: all Deno-related additions are wrapped in `try/except` to avoid breaking existing flows.

---

## 🆚 Updated Dependencies

- **yt-dlp:** `2025.12.08`
- **ffmpeg:** `8.0.1`  
- **deno:**  `2.5.6`

---

## 📥 Downloads

#### 🪟 Windows · x86_64 · 150 MB  
[⬇ Download for Windows](https://github.com/ErfanNamira/ytget-gui/releases/download/2.5.2/YTGet-windows.zip)

#### 🐧 Linux · x86_64 · 180 MB  
[⬇ Download for Linux](https://github.com/ErfanNamira/ytget-gui/releases/download/2.5.2/YTGet-linux.tar.gz)

#### 🍎 macOS (ARM) · arm64 · 100 MB  
[⬇ Download for macOS ARM](https://github.com/ErfanNamira/ytget-gui/releases/download/2.5.2/YTGet-macOS-arm64.tar.gz)

#### 🍎 macOS (Intel) · x86_64 · 100 MB  
[⬇ Download for macOS Intel](https://github.com/ErfanNamira/ytget-gui/releases/download/2.5.2/YTGet-macOS-x86_64.tar.gz)

---


### 📊 VirusTotal Scan
🔗 [View scan results on VirusTotal](https://www.virustotal.com)  

_The archive contains `.exe` files, which may still occasionally be flagged by some antivirus engines as **false positives**. These are not actual threats._  
