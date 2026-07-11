## ✨ What's New
### 🪟 Windows Installer
- Added a lightweight Windows installer (`YTGet-Setup.exe`) built with Inno Setup. It fetches yt-dlp, ffmpeg/ffprobe, deno, and SpotDL during setup, keeping the installer download small and installation streamlined.
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
      <td rowspan="3">🪟 <strong>Windows</strong></td>
      <td rowspan="3"><code>x86_64</code></td>
      <td>ZIP</td>
      <td><strong>255 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.3/YTGet-windows.zip">
          <img src="https://img.shields.io/badge/Download-ZIP-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows ZIP Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>165</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.3/YTGet-windows.7z">
          <img src="https://img.shields.io/badge/Download-7z-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows 7z Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>Installer (.exe)</td>
      <td><strong>Small</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.3/YTGet-Setup.exe">
          <img src="https://img.shields.io/badge/Download-Installer-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows Installer Download">
        </a>
      </td>
    </tr>
    <tr>
      <td rowspan="2">🐧 <strong>Linux</strong></td>
      <td rowspan="2"><code>x86_64</code></td>
      <td>tar.gz</td>
      <td><strong>255 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.3/YTGet-linux.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>190</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.3/YTGet-linux.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.3/YTGet-macOS-arm64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>105</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.3/YTGet-macOS-arm64.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.3/YTGet-macOS-x86_64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>110</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.3/YTGet-macOS-x86_64.7z">
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
