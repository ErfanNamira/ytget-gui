# 🎬 YTGet GUI — YouTube Downloader
YTGet GUI is a sleek, user-friendly desktop application built with Python and PySide6 to help you download YouTube videos and playlists effortlessly using yt-dlp. This Windows .exe version is packaged and portable — no Python installation required.
## ☄️ How to run?
Download the latest .zip release, extract it, and run YTGet.exe.

## ✨ Features
    🎯 Clean Qt GUI — Intuitive design with dark friendly visuals.
    📥 Download formats — Choose from multiple resolutions up to 4K, or audio-only (MP3).
    🎵 MP3 Mode — Extract high-quality audio with thumbnails and metadata.
    📃 Auto Subtitles — Automatically fetch English subtitles (if available).
    📂 Playlist Support — Download entire playlists in audio mode.
    📡 No external dependencies — Comes with bundled yt-dlp, ffmpeg, and ffprobe.
    🪟 Fully Offline Capable — No need for runtime Python installation.
    🛑 Cancel Anytime — Gracefully terminate downloads mid-process.

# 🖼 Screenshot
<p align="center"> <img src="https://raw.githubusercontent.com/ErfanNamira/YTGet/main/Imagez/YTGet1.1.7.jpg" alt="YTGet GUI"> </p>

## 🧰 How to Use
    📦 Extract the downloaded .zip file.
    ▶️ Double-click YTGet.exe to launch the app.
    🔗 Paste your YouTube URL in the input box.
    🔥 Select Format (e.g. 1080p MKV or MP3 Audio).
    ⬇️ Click Download — Sit back and watch the log in real time!
    💡 You can cancel any ongoing download by clicking the same button again.

## 📁 Output
    ✅ Saved using clean filenames (%(title)s.ext)
    🎵 Audio downloads include:
        Embedded album art (from thumbnail)
        Metadata tags
        English subtitles (if available)

## 🧩 Format Options
    🎢 480p - 2160p	MKV Video with merged best audio
    🎵 MP3 Audio	    High-quality MP3 with thumbnail + tags
    🎵 MP3 Playlist    	Extract audio from full playlist

## 🔒 Cookies Support
To enable downloading age-restricted or private videos, place your exported cookies.txt file in the following directory:
```
_internal/cookies.txt
```
You can export cookies.txt using browser extensions like Get cookies.txt and save it inside the _internal folder included with the app.

## ⚙️ Requirements
    ✅ No installation needed — fully portable
    ✅ Windows 10 or later (64-bit)
    
## 📄 License
This project is licensed under the MIT License. See the LICENSE file for details.

## 📦 Download
👉 [Latest Release (.zip)](https://github.com/ErfanNamira/YTGet/releases/latest)
