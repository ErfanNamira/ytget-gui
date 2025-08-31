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

### 🪟 Windows
1. [Download the latest `YTGet-Windows.zip` release.](https://github.com/ErfanNamira/ytget-gui/releases/latest/download/YTGet-Windows.zip)  
2. Extract the contents.  
3. Run `YTGet.exe`.

### 🐧 Linux
1. Install required dependencies:
```
sudo apt-get update && sudo apt-get install -y libxcb-cursor0 libxcb-xinerama0 libxcb-xinput0 libxcb-xfixes0 libxcb-shape0 libxcb-render-util0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render0 libxcb-shm0 libxcb-sync1 libxcb-util1 libxcb-xkb1
``` 
2. [Download the latest `YTGet-Linux.tar.gz` release.](https://github.com/ErfanNamira/ytget-gui/releases/latest/download/YTGet-Linux.tar.gz)  
3. Extract the contents.
```
tar -xzf YTGet-Linux.tar.gz
```
4. Make it executable and launch:
```
chmod +x YTGet
./YTGet
```

### 🍎 macOS
1. Download the latest `YTGet-macOS.tar.gz` release.

[Apple Silicon (arm64)](https://github.com/ErfanNamira/ytget-gui/releases/download/2.4.7/YTGet-macOS.tar.gz)

[Intel (amd64)](https://github.com/ErfanNamira/ytget-gui/releases/download/2.4.7/YTGet-macOS-x86_64.tar.gz)

2. In Terminal, run:
```
tar -xzf YTGet-macOS.tar.gz
```
This will produce a YTGet.app bundle in your current directory.

3. Remove Quarantine Flag
If you see “cannot be opened because Apple cannot check it for malicious software,” you need to strip the quarantine attribute:
```
xattr -d com.apple.quarantine YTGet.app
```
This lets macOS trust your app without popping security dialogs every launch.

4. Set Executable Permission
```
chmod +x YTGet.app/Contents/MacOS/YTGet
```
5. Move to Applications (Optional)
   
For a cleaner setup, drag YTGet.app into your /Applications folder or run:
```
mv YTGet.app /Applications/
```
6. Launch YTGet
   
Choose one:
* From Finder: double-click /Applications/YTGet.app.
* From Terminal:
  ```
  open /Applications/YTGet.app
  ```
* Or run the binary directly:
  ```
  /Applications/YTGet.app/Contents/MacOS/YTGet
  ``` 
<!--
### 🍎 macOS (dmg)
1. [Download the latest YTGet-macOS.dmg release.]()
2. Double-click the .dmg to mount it.
3. Drag YTGet.app from the mounted volume into your Applications folder.
4. Eject the mounted image (right-click in Finder → Eject).
5. Launch From Finder: open /Applications/YTGet.app
6. If Gatekeeper blocks first launch, right-click (or Control-click) YTGet.app → Open, then confirm.
-->
### 🐍 [PyPI Installation](https://pypi.org/project/ytget-gui/)
YTGet GUI depends on FFmpeg to process and convert media. Follow these steps to get everything up and running:

#### 1️⃣ Install YTGet GUI
```
pip install ytget-gui
```
#### 2️⃣ Set Up FFmpeg

Choose one of the two methods below:

**2.1 Add FFmpeg to Your PATH (Recommended)**
* Download the latest FFmpeg build for your platform from this [Link](https://ffmpeg.org/download.html).
* Extract the archive.
* Add the bin/ directory to your system PATH:
 
    On Windows: update Environment Variables → Path.
  
    On macOS/Linux: edit ~/.bashrc or ~/.zshrc with
    ```
    export PATH="/path/to/ffmpeg/bin:$PATH"
    ```
* Verify installation:
  ```
  ffmpeg -version
  ```
**2.2 Copy Binaries into the YTGet Folder (Alternative)**

  * Download the static FFmpeg binaries for your OS.

  * Copy ffmpeg (or ffmpeg.exe) and ffprobe (or ffprobe.exe) into the same directory where the ytget-gui executable lives. 

#### 🔄 How to Update (PyPI version)

To upgrade your PyPI installation to the latest release:
```
pip install --upgrade ytget-gui
```
This command fetches and installs the newest version, replacing your current one automatically.

#### ✨ Extra Tips You Might Find Useful
* On macOS, you can also use Homebrew:
```
brew install ffmpeg
```
* On Debian/Ubuntu:
```
sudo apt update && sudo apt install ffmpeg
```

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

1. ▶️ Launch `YTGet`.  
2. 🔗 Paste a YouTube URL.  
3. 🎚️ Select format (e.g., 1080p MKV or MP3).  
4. ⬇️ Click **➕ Add to Queue**.  
5. ⬇️ Click **▶️ Start Queue**.

---

## 📁 Output

- ✅ Clean filenames: `%(title)s.ext`  
- 🎵 Audio downloads include:
  - Embedded album art  
  - Metadata tags (artist, title, etc.)  

---

## 🧩 Format Options

| Format           | Description                                     |
|-----------------|-------------------------------------------------|
| 🎞️ 480p–8K      | MKV, MP4, WebM video with merged best audio               |
| 🎵 FLAC Audio    | High-quality audio with tags & thumbnails      |
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
