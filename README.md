# 🎬 YTGet — Cross-Platform YouTube Downloader

**YTGet GUI** is a modern, lightweight, and user-friendly desktop application built with **Python** and **PySide6**.  
Powered by **yt-dlp**, it makes downloading YouTube videos, playlists, and music simple and efficient.  

- 🖥️ **Cross-Platform:** Runs seamlessly on **Windows**, **macOS**, and **Linux**.  
- 📦 **Standalone:** Each release comes with all dependencies bundled, so it works right out of the box.  
- ⚡ **Optimized & Stable:** Designed for smooth performance with smart resource handling, and built-in update management.  
- 🎵 **Versatile:** Supports full videos, playlists, and music downloads in multiple formats.  

Whether you’re grabbing a single clip or archiving an entire channel, **YTGet** delivers a polished and seamless experience on every operating system.

---

## 📊 Repository Stats

### 🌟 Community
![GitHub repo stars](https://img.shields.io/github/stars/ErfanNamira/ytget-gui?style=for-the-badge&logo=github)
![GitHub forks](https://img.shields.io/github/forks/ErfanNamira/ytget-gui?style=for-the-badge&logo=github)
![GitHub watchers](https://img.shields.io/github/watchers/ErfanNamira/ytget-gui?style=for-the-badge&logo=github)

### 🐛 Issues & 🔀 Pull Requests
![GitHub issues](https://img.shields.io/github/issues/ErfanNamira/ytget-gui?style=for-the-badge)
![GitHub closed issues](https://img.shields.io/github/issues-closed/ErfanNamira/ytget-gui?style=for-the-badge)
![GitHub pull requests](https://img.shields.io/github/issues-pr/ErfanNamira/ytget-gui?style=for-the-badge)
![GitHub closed PRs](https://img.shields.io/github/issues-pr-closed/ErfanNamira/ytget-gui?style=for-the-badge)

### 📥 Downloads
![GitHub all releases](https://img.shields.io/github/downloads/ErfanNamira/ytget-gui/total?label=Total%20Downloads&style=for-the-badge)
![GitHub release (latest by date)](https://img.shields.io/github/downloads/ErfanNamira/ytget-gui/latest/total?label=Latest%20Release&style=for-the-badge)

### 💻 Codebase
![GitHub repo size](https://img.shields.io/github/repo-size/ErfanNamira/ytget-gui?style=for-the-badge)
![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/ErfanNamira/ytget-gui?style=for-the-badge)
![GitHub language count](https://img.shields.io/github/languages/count/ErfanNamira/ytget-gui?style=for-the-badge)
![GitHub top language](https://img.shields.io/github/languages/top/ErfanNamira/ytget-gui?style=for-the-badge)

### ⏱️ Activity
![GitHub last commit](https://img.shields.io/github/last-commit/ErfanNamira/ytget-gui?style=for-the-badge)
![GitHub commit activity](https://img.shields.io/github/commit-activity/m/ErfanNamira/ytget-gui?style=for-the-badge)

---

## ☄️ How to Install

### 📦 Windows
1. Download the latest `YTGet-Windows.zip` release.  
2. Extract the contents.  
3. Run `YTGet.exe`.

### 🐧 Linux
1. Download the latest `YTGet-Linux.tar.gz` release.  
2. Extract the contents.
```
tar -xzf YTGet-ubuntu-latest.tar.gz
```
3. Make it executable and launch:
```
chmod +x YTGet
./YTGet
```

### 🍏 macOS
1. Download the latest `YTGet-macOS.tar.gz` release.  
2. Extract the contents.
```
tar -xzf YTGet-macos-latest.tar.gz
```
3. If macOS blocks the app, remove the quarantine flag:
```
xattr -d com.apple.quarantine YTGet.app
```
4. Launch from Finder or via Terminal:
```
open YTGet.app
```
Or run directly:
```
chmod +x YTGet.app/Contents/MacOS/YTGet
YTGet.app/Contents/MacOS/YTGet
```

### 🐍 [PyPI Installation](https://pypi.org/project/ytget-gui/)
YTGet requires FFmpeg to process media. You can set it up in one of the following ways:

#### 1️⃣ Add FFmpeg to PATH (Recommended)

Download the latest FFmpeg build. Extract it and add the bin/ folder to your system PATH so that the ffmpeg command is available globally.

#### 2️⃣ Place Binaries in the Program Folder (Alternative)

Download the FFmpeg binaries. Copy ffmpeg.exe and ffprobe.exe into the YTGet installation directory (the same folder as the executable).

#### 3️⃣ Install YTGet via pip:

```bash
pip install ytget-gui
```
### 🔄 How to Update (PyPI version)

To update YTGet GUI installed via pip:
```
pip install --upgrade ytget-gui
```
This will fetch the latest version from PyPI and replace the old version automatically.

---

## ✨ Features

### 🖥️ Interface
- 🎯 **Clean Qt GUI** — Intuitive layout with dark-friendly visuals.  
- 🛑 **Cancel Anytime** — Gracefully stop downloads at any moment.  
- 🔒 **Offline Capable** — No Python installation required.

### 📥 Download Options
- 📹 **Multiple Formats** — Download videos from 480p up to 8K.  
- 🎵 **MP3 Mode** — High-quality audio extraction with embedded thumbnails & metadata.  
- 📄 **Subtitles** — Auto-fetch subtitles (multi-language).  
- 📂 **Playlist Support** — Download entire playlists in audio/video mode.

### 🔧 Advanced Features
- ⚙️ **Persistent Settings** — All settings saved to `config.json`.  
- 🚀 **Improved Playlist Support** — Reverse order, select items, archive tracking.  
- ✂️ **Clip Extraction** — Download video portions by start/end time.  
- ⏭️ **SponsorBlock** — Skip sponsored content, intros, and outros.  
- 🧩 **Chapters Handling** — Embed or split videos by chapters.  
- 🎼 **YouTube Music Metadata** — Accurate music info and album data.

### 🛠 Functionality
- 🌐 **Proxy Support** — Configure proxies for downloads.  
- 📅 **Date Filter** — Download videos uploaded after a specified date.  
- 🧪 **Custom FFmpeg Args** — Add advanced arguments for power users.  
- 🔊 **Audio Normalization** — Uniform volume for all downloads.  
- 🗃 **Channel Organization** — Auto-sort videos into uploader folders.  
- ⚡ **Performance Enhancements** — Smart rate limiting and retry logic.

---

## 🖼 Screenshots

<p align="center">
  <img src="https://raw.githubusercontent.com/ErfanNamira/YTGet/refs/heads/main/Images/YTGet2.4%20(1).JPG" width="220" />
  <img src="https://raw.githubusercontent.com/ErfanNamira/YTGet/refs/heads/main/Images/YTGet2.4%20(2).JPG" width="220" />
  <img src="https://raw.githubusercontent.com/ErfanNamira/YTGet/refs/heads/main/Images/YTGet2.4%20(3).JPG" width="220" />
  <img src="https://raw.githubusercontent.com/ErfanNamira/ytget/refs/heads/main/Images/YTGet2.4.3.JPG" width="220" />
</p>

---

## 🧰 How to Use

1. 📦 Extract the downloaded `.zip` file.  
2. ▶️ Launch `YTGet.exe`.  
3. 🔗 Paste a YouTube URL.  
4. 🎚️ Select format (e.g., 1080p MKV or MP3).  
5. ⬇️ Click **➕ Add to Queue**.  
6. ⬇️ Click **▶️ Start Queue**.

---

## 📁 Output

- ✅ Clean filenames: `%(title)s.ext`  
- 🎵 Audio downloads include:
  - Embedded album art  
  - Metadata tags (artist, title, etc.)  
  - Subtitles (if available)

---

## 🧩 Format Options

| Format           | Description                                     |
|-----------------|-------------------------------------------------|
| 🎞️ 480p–8K      | MKV video with merged best audio               |
| 🎵 MP3 Audio     | High-quality audio with tags & thumbnails      |
| 📃 Playlist MP3  | Batch audio extraction from playlists          |

---

## 🔒 Cookies Support

For **age-restricted** or **private content**:

1. Export cookies using [Get cookies.txt](https://chrome.google.com/webstore/detail/get-cookiestxt/lgmpjfekhdgcmpcpnmlhkfkfjdkpmoec) extension.  
2. Place the file in `_internal/cookies.txt`.

---

## ⚙️ Requirements

- ✅ No installation — just unzip and run.  
- 🪟 Windows 10+ (64-bit).

---

## 🔧 Development Setup

### Prerequisites

- [Python 3.13+](https://www.python.org/downloads/)  
- [FFmpeg](https://www.ffmpeg.org/download.html) (Add to PATH or project folder)

### Setup

```bash
# Clone the repo
git clone https://github.com/ErfanNamira/ytget-gui.git

# Navigate to project
cd ytget-gui

# Create & activate virtual environment
python -m venv venv
# Linux/Mac
source venv/bin/activate
# Windows
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run app
python -m ytget_gui
```
---

## 🤝 Contribution Guide

1. Fork & clone the repo

2. Create a feature branch: git checkout -b my-feature

3. Commit & push: git commit -m "msg" && git push origin my-feature

4. Open a Pull Request

---

## 📄 License

This project is licensed under the **MIT License**. See the [LICENSE](./LICENSE) file for full details.

---

## 📦 Download

👉 [Latest Release (.zip)](https://github.com/ErfanNamira/YTGet/releases/latest)