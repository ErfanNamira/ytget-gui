## ✨ What's New

### 🎧 Opus Audio Support
- Added Opus format codes for both single tracks and playlists (`audio_opus`, `playlist_opus`), with matching one-click presets.
- `.opus` files are now recognized during post-processing.

### 🎶 Playlist & Format Cleanup
- Merged the old `youtube_music` format into `playlist_mp3` — YouTube Music metadata parsing now applies to any playlist audio download (MP3 or Opus) when enabled in settings.
- Consolidated duplicate MP3 playlist presets into a single 🎶 Audio Playlist (MP3 – YouTube/Music) preset.

### 🔧 More Reliable Spotify Downloads
- Increased default SpotDL parallelism (6 → 12 threads).
- Added an automatic YouTube fallback provider so a single provider hiccup no longer causes a track to silently fail.
- Fixed misleading "success" messages — SpotDL runs now flag any tracks that actually failed, even when the underlying process exits with code 0.

### 🎨 Lighter Dark Theme
- Rebalanced near-black surfaces to a richer dark grey/blue across the app for better readability. Accent colors are unchanged.

### 🧹 Simplified About Dialog & Update Manager
- Removed FFmpeg/FFprobe checks from the Update Manager.
- Streamlined the About dialog down to "About" and "License" tabs.
- Fixed a brief console window flash during update checks on Windows.

### 🐛 Fixed YouTube Music Track Numbers
- Track numbers now correctly reflect each track's actual playlist position instead of a bogus fixed value.

---

## 🆚 Updated Dependencies

- **yt-dlp:** `2026.07.04`
- **ffmpeg:** `8.1.2`  
- **deno:**  `2.9.2`
- **SpotDL (Windows only):**  `4.5.0`

---

## 📥 Downloads

#### 🪟 Windows · x86_64 · 230 MB  
[⬇ Download for Windows](https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.1/YTGet-windows.zip)

#### 🐧 Linux · x86_64 · 255 MB  
[⬇ Download for Linux](https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.1/YTGet-linux.tar.gz)

#### 🍎 macOS (ARM) · arm64 · 155 MB  
[⬇ Download for macOS ARM](https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.1/YTGet-macOS-arm64.tar.gz)

#### 🍎 macOS (Intel) · x86_64 · 158 MB  
[⬇ Download for macOS Intel](https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.1/YTGet-macOS-x86_64.tar.gz)

---

### 📊 VirusTotal Scan
🔗 [View scan results on VirusTotal](https://www.virustotal.com)  

_The archive contains `.exe` files, which may still occasionally be flagged by some antivirus engines as **false positives**. These are not actual threats._
