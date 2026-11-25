<div align="center">

<img src="https://erfannamira.github.io/ytget-gui/assets/img/logo.png" width="110" alt="YTGet logo" />

# YTGet

**A modern, cross-platform YouTube downloader — powered by yt-dlp**

[![Release](https://img.shields.io/github/v/release/ErfanNamira/ytget-gui?style=flat-square&label=release)](https://github.com/ErfanNamira/ytget-gui/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](./LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-blue?style=flat-square)](#-installation)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-yellow?style=flat-square&logo=python&logoColor=white)](#-development-setup)
[![PyPI](https://img.shields.io/pypi/v/ytget-gui?style=flat-square&label=pypi)](https://pypi.org/project/ytget-gui/)
[![Downloads](https://img.shields.io/github/downloads/ErfanNamira/ytget-gui/total?style=flat-square&label=downloads)](https://github.com/ErfanNamira/ytget-gui/releases)
[![Stars](https://img.shields.io/github/stars/ErfanNamira/ytget-gui?style=flat-square)](https://github.com/ErfanNamira/ytget-gui/stargazers)

**English** | [فارسی](./README.fa.md)

[Website](https://erfannamira.github.io/ytget-gui/) · [Releases](https://github.com/ErfanNamira/ytget-gui/releases) · [What's New](./CHANGELOG.md)

</div>

---

YTGet is a lightweight desktop app, built with **Python** and **PySide6**, that wraps the power of
**yt-dlp** in a clean, friendly queue-based interface. Paste a link, pick a format, hit Start —
grab a single clip or archive an entire channel, with full control over naming, pacing and output.

- 🖥️ **Cross-platform** — Windows, macOS and Linux, each with standalone builds that bundle every dependency.
- 🎞️ **480p → 8K video, MP3/FLAC/Opus audio** — with embedded art, tags and metadata.
- 🔄 **A real queue** — hundreds of items, live progress and size estimates, background saves, instant stop.
- 🤖 **Automation built in** — clipboard watcher, system tray, scheduler, run at sign-in.
- 🛡️ **Keeps up with YouTube** — smart client/Deno handling for recent yt-dlp extractor changes, and an anti-429 pacing preset.

---

## 🖼 Screenshots

<p align="center">
  <img src="https://erfannamira.github.io/ytget-gui/assets/img/app-main.jpg" alt="YTGet main window" width="795" />
  <img src="https://erfannamira.github.io/ytget-gui/assets/img/app-queue.jpg" alt="YTGet download queue" width="795" />
</p>
<p align="center">
  <img src="https://erfannamira.github.io/ytget-gui/assets/img/app-advanced.jpg" alt="Advanced per-item options" width="385" />
  <img src="https://erfannamira.github.io/ytget-gui/assets/img/app-prefs.jpg" alt="Preferences" width="385" />
</p>

---

## 🆕 What's New in 2.8.5

- 🔄 **Change the recording type of queued items in place** — select rows and use the bulk bar's **TYPE** button (or right-click → *Change recording type…*) to switch them to any preset. Items keep their position, details and thumbnail; the dialog itself is ~30% wider so nothing is cramped.
- 🧩 **Fix for "Requested format is not available"** — handles every known way the yt-dlp 2026.10.26+ YouTube extractor can fail: the bundled Deno is only used when it's ≥ 2.3.0, metadata fetches recover by falling back from a pinned player client, and the queue log now shows *why* formats went missing. The Nov-2026 EJS challenge-solver crash is detected and reported as a yt-dlp update need instead of being retried forever.
- 📏 **Codec-aware size estimates** — queue cards quote the size for the codec (AV1/VP9/AVC) your format actually prefers.
- ⏱️ **Request pacing: preset or custom** — the recommended anti-429 sleep spacing now lives in **Preferences → Advanced → Request pacing** instead of the Extra arguments field; pick the Sleep preset or dial in your own four values.
- 🛡️ **Subtitle 429 resilience** — a rate-limited subtitle download disables subtitles for that item's retries instead of failing the whole download.
- 📏 Long titles can no longer stretch the queue layout.

See the full history in [CHANGELOG.md](./CHANGELOG.md) and [RELEASE_NOTES.md](./RELEASE_NOTES.md).

---

## 📥 Installation

### 🪟 Windows

**Installer (recommended)** — download `YTGet-<version>-windows-setup.exe` from the
[releases page](https://github.com/ErfanNamira/ytget-gui/releases/latest) and run it.
It installs for the current user only (no admin prompt), with optional desktop shortcut
and "start at sign-in".

**Portable** — download [`YTGet-windows.zip`](https://github.com/ErfanNamira/ytget-gui/releases/latest/download/YTGet-windows.zip) (`.7z` also available), extract, run `YTGet.exe`.

### 🐧 Linux

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg python3-mutagen \
  libxcb-cursor0 libxcb-xinerama0 libxcb-xinput0 libxcb-xfixes0 libxcb-shape0 \
  libxcb-render-util0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
  libxcb-render0 libxcb-shm0 libxcb-sync1 libxcb-util1 libxcb-xkb1
```

Then download [`YTGet-linux.tar.gz`](https://github.com/ErfanNamira/ytget-gui/releases/latest/download/YTGet-linux.tar.gz) and:

```bash
tar -xzf YTGet-linux.tar.gz && chmod +x YTGet && ./YTGet
```

### 🍎 macOS

Download the build for your Mac —
[Apple Silicon (arm64)](https://github.com/ErfanNamira/ytget-gui/releases/latest/download/YTGet-macOS-arm64.tar.gz) ·
[Intel (x86_64)](https://github.com/ErfanNamira/ytget-gui/releases/latest/download/YTGet-macOS-x86_64.tar.gz) —
then:

<details>
<summary>Setup steps (first launch)</summary>

```bash
cd Downloads
tar -xzf YTGet-macOS-arm64.tar.gz        # or YTGet-macOS-x86_64.tar.gz
xattr -d com.apple.quarantine YTGet.app  # skip Gatekeeper warning
chmod +x YTGet.app/Contents/MacOS/YTGet
mv YTGet.app /Applications/              # optional
open /Applications/YTGet.app
```

</details>

> On macOS, also run **Help → Check yt-dlp Update** once after the first launch.

### 🐍 PyPI

```bash
pip install ytget-gui          # install
pip install --upgrade ytget-gui  # update later
```

The PyPI build needs **FFmpeg**: either add it to your `PATH`, or drop `ffmpeg`/`ffprobe`
binaries next to the executable. On macOS `brew install ffmpeg`, on Debian/Ubuntu
`sudo apt install ffmpeg`.

---

## 🧰 Quick Start

1. ▶️ Launch **YTGet** and paste a YouTube URL.
2. 🎚️ Pick a format — e.g. 1080p MKV or MP3.
3. ⚙️ Optional: open **Advanced** to arm a clip range or playlist selection *for the next item you add* (the button shows a dot while armed).
4. ➕ Click **Add to Queue**. Want the same link in another format? Pick it and add again — each format is its own row.
5. ▶️ Click **Start Queue**.

For hands-off downloading, enable **Tools → Clipboard Watcher** (`Ctrl+Shift+V`) and just copy links — 76 sites are recognized, with a separate default format per category (YouTube, YouTube Music, Spotify, other).

---

## ✨ Features

| | |
|---|---|
| 🎞️ **Video 480p → 8K** | MKV / MP4 / WebM with merged best audio |
| 🎵 **Audio extraction** | MP3, FLAC and Opus with embedded art, tags and metadata |
| 📂 **Playlists** | Full or selected items, reverse order, archive tracking |
| 🔁 **Same link, several formats** | Queue one video as 1080p *and* MP3 — each is its own row |
| 🔄 **Change recording type in place** | Switch queued items to any preset without re-adding |
| 📏 **Size estimates** | Codec-aware, per queue card |
| ✂️ **Clip extraction** | Download a portion by start/end time, per item |
| ⏭️ **SponsorBlock** | Skip sponsors, intros and outros |
| 🧩 **Chapters** | Embed or split by chapters |
| 🎼 **YouTube Music metadata** | Accurate music info and album data |
| 📄 **Subtitles** | Auto-fetch, multi-language |
| 🌐 **Proxy support** | Route downloads through a proxy |
| 📅 **Date filter** | Only videos uploaded after a set date |
| 🔊 **Audio normalization** | Uniform volume across downloads |
| 🧪 **Custom FFmpeg args** | For power users |
| 🗃 **Channel organization** | Auto-sort into uploader folders |
| 🖱️ **System tray** | Control the queue without opening the window |
| 📋 **Clipboard watcher** | Auto-queue any link you copy |
| ⏰ **Scheduler** | Start/stop the queue at set times |
| 🚀 **Run at sign-in** | Launch minimized to tray |
| 📄 **Link import/export** | Read a link list from (or save the queue to) a text file |
| ⏱️ **Request pacing** | Anti-429 sleep preset or fully custom spacing in Advanced |
| 🔄 **Update manager** | App, yt-dlp and Deno updates from **Help → Check for Updates** |
| 🩺 **Logs & crash reports** | `ytget.log` / `crash.log` via **Help → Open Logs Folder** |

---

## 📁 Output & Naming

- Clean filenames by default: `%(title)s.ext`.
- **Per-site naming rules** (Preferences → Output): separate filename styles for **YouTube**, **YouTube Music** and **Other sites**, each split into **Video** and **Audio** — e.g. `Artist - Track # Title` for music, `Uploader - Title` for videos. Every slot starts on *Use general setting*, so nothing changes until you pick something.
- Audio downloads include embedded album art (cropped 1:1) and metadata tags.
- Two different uploads with the same title (e.g. a single and the album version on a Music "Topic" channel) are both kept — the second is saved as `Title [video-id].ext`.
- Logs and crash reports live in the data folder under `logs`.

---

## 🔒 Cookies (private / age-restricted content)

1. Export cookies with the [Get cookies.txt](https://chrome.google.com/webstore/detail/get-cookiestxt/lgmpjfekhdgcmpcpnmlhkfkfjdkpmoec) extension.
2. Place the file at `_internal/cookies.txt`.

---

## 🩺 Troubleshooting

- **"Requested format is not available"** — make sure yt-dlp and Deno are up to date (**Help → Check for Updates**, each is one click). If the startup banner warns about Deno, update it once.
- **"n challenge solving failed" / "Only images are available"** — a known yt-dlp bug with YouTube's late-November 2026 players, fixed in **yt-dlp 2026.11.23**. Update yt-dlp via **Help → Check for Updates**; YTGet detects this failure and marks the item with instructions instead of retrying it. It's not a Deno, cookies or proxy problem.
- **Frequent HTTP 429 rate limits** — enable **Sleep (gentle spacing)** under **Preferences → Advanced → Request pacing**, or choose **Custom** and set your own four sleep values.
- Some formats are limited or temporarily unavailable on YouTube itself; if one keeps failing, an yt-dlp update may be needed.

---

## 🔧 Development Setup

**Prerequisites:** [Python 3.13+](https://www.python.org/downloads/), [FFmpeg](https://www.ffmpeg.org/download.html) on PATH or in the project folder.

```bash
git clone https://github.com/ErfanNamira/ytget-gui.git
cd ytget-gui
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python -m ytget_gui             # run the app
python -m pytest                # run the test suite
```

---

## 🤝 Contributing

1. Fork & clone the repo
2. Create a feature branch: `git checkout -b my-feature`
3. Commit & push: `git commit -m "msg" && git push origin my-feature`
4. Open a Pull Request

---

## 🙏 Acknowledgements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — the engine that does the actual downloading.
- [PySide6 / Qt](https://www.qt.io/qt-for-python) — the UI toolkit.

---

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](./LICENSE).

---

## 📦 Download

👉 [Latest Release](https://github.com/ErfanNamira/ytget-gui/releases/latest)
