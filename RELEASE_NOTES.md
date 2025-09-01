## ✨ What’s New

🎬 **Video-Cover Embedding**  
   - Added a new Embed Thumbnail option for video downloads (.mkv, .mp4, .webm).  
   - When enabled, yt-dlp runs --embed-thumbnail plus FFmpeg metadata flags to set the downloaded thumbnail as the file’s cover art.  

🖼️ **Thumbnail Download & Conversion Controls** 
   - Download Thumbnails toggle saves the original thumbnail alongside the media file.
   - Convert Thumbnail to PNG toggle converts the saved thumbnail into .png format.
   - Controls are exposed in the **Preferences → Post-processing page**.

## 🛠️ Bug Fixes & Improvements

🎨 **Fixed Preferences Dialog Palette** 
   - The Preferences window forces a dark, high-contrast background (#161A22) and light text (#EAEFF2), preventing unreadable text when the OS or Qt theme changes on macOS/Linux.

---
## 📥 Downloads  

| Platform          | Architecture                               | File Size | Download |
|-------------------|-------------------------------------------|--------------------|----------|
| 🪟 **Windows**    | ![x86_64](https://img.shields.io/badge/arch-x86__64-blue) | ~150 MB            | [![Download](https://img.shields.io/badge/Download-Windows-blue?logo=windows)](https://github.com/ErfanNamira/ytget-gui/releases/download/2.4.9/YTGet-windows.zip) |
| 🐧 **Linux**      | ![x86_64](https://img.shields.io/badge/arch-x86__64-green) | ~180 MB            | [![Download](https://img.shields.io/badge/Download-Linux-green?logo=linux)](https://github.com/ErfanNamira/ytget-gui/releases/download/2.4.9/YTGet-linux.tar.gz) |
| 🍎 **macOS**      | ![arm64](https://img.shields.io/badge/arch-arm64-orange)   | ~100 MB            | [![Download](https://img.shields.io/badge/Download-macOS-orange?logo=apple)](https://github.com/ErfanNamira/ytget-gui/releases/download/2.4.9/YTGet-macOS-arm64.tar.gz) |
| 🍎 **macOS**      | ![x86_64](https://img.shields.io/badge/arch-x86__64-orange)| ~100 MB            | [![Download](https://img.shields.io/badge/Download-macOS-orange?logo=apple)](https://github.com/ErfanNamira/ytget-gui/releases/download/2.4.9/YTGet-macOS-x86_64.tar.gz) |

---

### 🆚 Updated Dependencies
- **yt-dlp:** `2025.08.27`  
- **ffmpeg:** `8.0.0`  

---

### 📊 VirusTotal Scan
🔗 [View scan results on VirusTotal](https://www.virustotal.com)  

_The archive contains `.exe` files, which may still occasionally be flagged by certain antivirus engines as **false positives**. These are not actual threats._
