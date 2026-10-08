# ✨ What's New v2.8.3

## Release summary

YTGet 2.8.3 fixes the app closing on its own in the middle of a download and
adds per-site, per-recording-type file naming. Your settings and queue carry
over untouched, and every file is still named exactly as before until you
choose otherwise.

---

## ⚡ Highlights

### 🛡️ No more silent closes mid-download

- **Fixed a crash between and during downloads.** When an item finished, the
  queue released its download thread a moment before that thread had fully
  stopped. Depending on timing this crashed the whole app with no error
  message — in the packaged build *and* when run from source. A stress test
  that crashed 2.8.2 on every run now passes reliably.
- **Fixed the app quitting while minimised to the tray.** With the window in
  the tray, closing *any* dialog (Preferences, About, Check for Updates, or the
  clipboard watcher's "queue this link?" prompt) made the app exit, ending
  the running download.
- A bug inside a download no longer leaves the queue stuck on
  "Downloading": the item fails cleanly and the queue moves on.

### 🏷️ File names per site and per recording type

- New **Preferences → Output → Per-site naming** card with one setting each
  for **YouTube**, **YouTube Music** and **Other sites**, split into
  **Video** and **Audio**.
- Each slot can **Use general setting** (the default, which is the current
  behaviour), pick any preset, or use its **own custom template**. Set
  `Artist - Track # Title` for music and `Uploader - Title` for videos once,
  and never switch templates again. (Suggested by Mike — thank you!)
- New preset **Artist - Track # Title**. It falls back to the uploader when
  there is no artist and to the playlist position when there is no track
  number.

### 🩺 Crash reports you can actually send

- YTGet now keeps `ytget.log` and `crash.log` in its data folder (under
  `logs`). Native crashes, uncaught errors and Qt fatal messages are written
  there, even in the packaged build that has no console.
- **Help → Open Logs Folder** takes you straight to them.

### 🧹 Other fixes

- Cover cropping threads are shut down the same safe way as downloads.
- Thumbnail lookups clean up after themselves on their own thread.
- Startup no longer fails in headless tools that create a non-GUI Qt app.

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
      <td>Installer</td>
      <td><strong>205 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.3/YTGet-2.8.3-windows-setup.exe">
          <img src="https://img.shields.io/badge/Download-Setup-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows Installer Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>ZIP</td>
      <td><strong>255 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.3/YTGet-windows.zip">
          <img src="https://img.shields.io/badge/Download-ZIP-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows ZIP Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>165</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.3/YTGet-windows.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.3/YTGet-linux.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>190</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.3/YTGet-linux.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.3/YTGet-macOS-arm64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>105</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.3/YTGet-macOS-arm64.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.3/YTGet-macOS-x86_64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>110</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.3/YTGet-macOS-x86_64.7z">
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
