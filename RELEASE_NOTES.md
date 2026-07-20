## ✨ What's New

### 🔄 Queue & Drag-and-Drop Improvements
- Refactored queue handling so the visual order in the UI stays in sync with the internal queue state — fixes cases where drag-and-drop reordering could drift from what actually gets downloaded.
- Log filtering now correctly follows the synchronized queue order.
- Queue cards can now update their displayed title in place via a new internal `set_title` method, instead of requiring a full card rebuild.
- Improved thumbnail loading and metadata display on queue cards.

### 🖥️ UI & Rendering Fixes
- Fixed a truncation issue where the metadata label on queue cards wouldn't resize properly to fit its content.
- Styling functions now compute DPI scale and font size dynamically, improving appearance consistency across displays with different scaling settings.
- App style refresh is now correctly triggered after the application style is applied on launch.

### ⚙️ Preferences & Settings
- Refactored Preferences dialog field validators to share compiled regular expressions across dialog instances instead of recompiling them each time — reduces overhead when opening Preferences.
- Refactored regex patterns used for time and playlist validation.
- Settings retrieval now goes through a shared helper function, improving backward compatibility with settings saved by older versions of ytget.
- About dialog now reads settings via `getattr`, avoiding errors on missing/older settings keys.

### 📁 Default Downloads Folder
- The default downloads directory now prefers the user's real `~/Downloads` folder across all platforms (Windows, macOS, Linux), removing the previous platform-specific special-casing.

### 🛠️ Reliability & Internals
- Fixed output template file extension formatting.
- Fixed a formatting issue in the title fetcher.
- `_process_next` now uses an iterative loop instead of recursion for processing queued URLs — prevents a potential `RecursionError` when processing very large batches/playlists.
- Cleaned up `download_worker.py`: removed unused imports and streamlined log emission for clarity and efficiency.
- Update manager now has improved error handling and more robust installation paths.
- Application ID now includes the version number.

---
## 🆚 Updated Dependencies
- **yt-dlp:** `2026.07.04`
- **ffmpeg:** `8.1.2`  
- **deno:**  `2.9.3`
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
      <td rowspan="2">🪟 <strong>Windows</strong></td>
      <td rowspan="2"><code>x86_64</code></td>
      <td>ZIP</td>
      <td><strong>255 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.5/YTGet-windows.zip">
          <img src="https://img.shields.io/badge/Download-ZIP-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows ZIP Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>165</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.5/YTGet-windows.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.5/YTGet-linux.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>190</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.5/YTGet-linux.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.5/YTGet-macOS-arm64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>105</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.5/YTGet-macOS-arm64.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.5/YTGet-macOS-x86_64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>110</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.5/YTGet-macOS-x86_64.7z">
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
