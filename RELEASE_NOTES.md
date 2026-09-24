# ✨ What's New v2.8.1

## Release summary

YTGet 2.8.1 is a fix-up release for 2.8.0. The scheduler now really performs
its power action, Exit from the tray really closes the app, Windows shows the
right taskbar icon on the first launch after a boot, the queue stops
re-fetching titles it already has and starts retrying the ones it failed to
fetch, yt-dlp's own log can be switched back on, and any queue item can show
its thumbnail.

---

## ⚡ Highlights

### ⏰ The scheduler does what it says

- A scheduled shutdown, sleep or restart is no longer cancelled. It shared the
  "only when the whole queue completed" rule with the post-queue action, so a
  scheduled 07:00 sleep quietly did nothing whenever anything was still
  pending. A scheduled action now runs as instructed.
- A late tick can no longer step over a scheduled minute, a machine waking up
  hours later does not fire the missed action, and moving the clock backwards
  no longer mutes the scheduler for the rest of the day.

### ❌ Exit really exits

- Quitting from the tray while the window was hidden left YTGet running
  invisibly in Task Manager. The app now shuts down its event loop explicitly
  and exits for good once the queue and settings are saved.

### 🖼️ The right taskbar icon, every time

- YTGet identified itself to Windows with a different ID in every release, so
  the first launch after a boot showed the generic placeholder icon. The ID is
  now stable and the installer stamps it onto every shortcut.

### 📝 A queue that remembers what it fetched

- Titles are no longer re-fetched at every start. Items now record that their
  details were resolved instead of guessing from a missing size, which never
  arrives on many sites.
- Items that could not be fetched because of a rate-limit are retried
  automatically, with a growing backoff (1, 5, 15, 30 minutes, then hourly)
  that survives a restart. No more cards showing nothing but a URL forever.

### 🖥️ Optional yt-dlp log

- **Preferences → Advanced → Interface → Show yt-dlp output in the log panel**
  brings back the full download trail, including every entry of a playlist.
  Off by default: the queue card already shows per-item progress. Errors and
  warnings are always logged.

### 🖼️ View a thumbnail from the queue

- The `...` menu on a queue card has a new **View thumbnail** entry, with the
  image size, its cache path and an "Open in viewer" button. Items with no
  cached image just log a note and ask for it again.

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
      <td><strong>165 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.1/YTGet-2.8.1-windows-setup.exe">
          <img src="https://img.shields.io/badge/Download-Setup-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows Installer Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>ZIP</td>
      <td><strong>255 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.1/YTGet-windows.zip">
          <img src="https://img.shields.io/badge/Download-ZIP-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows ZIP Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>165</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.1/YTGet-windows.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.1/YTGet-linux.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>190</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.1/YTGet-linux.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.1/YTGet-macOS-arm64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>105</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.1/YTGet-macOS-arm64.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.1/YTGet-macOS-x86_64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>110</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.1/YTGet-macOS-x86_64.7z">
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
