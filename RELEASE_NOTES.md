# ✨ What's New v2.8.2

## Release summary

YTGet 2.8.2 is a performance and reliability release. Long queues stay
responsive, update checks no longer freeze when GitHub rate-limits you or
you're offline, Stop and quit react immediately, cached thumbnails load
without touching the network, and a handful of queue bugs are fixed.
Everything you already use works exactly as before; your settings and queue
carry over untouched.

---

## ⚡ Highlights

### 🏎️ A queue that stays smooth

- A failed item moving to the back of a long queue no longer freezes the
  window. Only the rows that moved are redrawn (~300 ms → ~4 ms for 81 items
  in testing), and scaled thumbnails are cached.
- The queue is saved in the background, a few hundred milliseconds after the
  last change, instead of after every single change on the UI thread.
- Removing many rows at once, and Clear completed, now take one pass.

### 🛑 Stop and quit mean now

- Stop, Skip and quitting interrupt every helper process, including the
  YouTube Music "Top songs / Mix / Radio" probe that could hold things up for
  30 seconds.
- Removing rows whose details are still loading cancels those lookups right
  away, instead of after every pending lookup has already run.
- If something refuses to stop, YTGet now exits cleanly after about ten
  seconds (queue and settings already saved) instead of hanging.
- Shutdown, restart and sleep after the queue (or on a schedule) no longer
  freeze the window and no longer flash a console window on Windows.

### 🔄 Update Manager that never hangs

- Checks run in parallel and the dialog closes instantly, even offline.
- GitHub rate limits are detected and bypassed; results are cached for 10
  minutes, and `GITHUB_TOKEN`/`GH_TOKEN` is used when set.
- Clear messages for offline, timeout, proxy and SSL problems.

### 🎵 Download fixes

- Playlists with two uploads sharing a title (a single and its album version)
  no longer fail forever with "Postprocessing: Conversion failed!"; the second
  one is saved as "Title [id]". This now works with the default settings too,
  not only with **Show yt-dlp output** turned on.
- MP3/M4A/FLAC: the first track's file keeps its own title, source URL and
  cover instead of being silently re-tagged with the second track's.
- The scary red "Conversion failed!" line for an already-existing file is
  replaced by a short explanation of what happens to that track.
- Playlist progress advances smoothly across the whole playlist, and the
  video bar no longer stalls at 50% between the video and audio streams.
- Audio normalisation works again instead of breaking every download.
- Cover cropping covers every track of a playlist, even when the playlist
  partly failed.

### 🧹 Queue fixes

- **Clear completed** no longer removes the pending 1080p row when the MP3 of
  the same link is the one that finished.
- **Play file**, **Show in folder** and **Copy file path** appear in the card
  menu as soon as a download finishes, not only after a restart.
- Thumbnails already on disk are shown immediately, without network requests.

### 🍎🐧 Platform fixes

- macOS: Run at login works for install paths containing `&` or `<`.
- Linux: Show in folder selects files whose names contain spaces, `#` or
  non-ASCII characters.

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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.2/YTGet-2.8.2-windows-setup.exe">
          <img src="https://img.shields.io/badge/Download-Setup-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows Installer Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>ZIP</td>
      <td><strong>255 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.2/YTGet-windows.zip">
          <img src="https://img.shields.io/badge/Download-ZIP-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows ZIP Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>165</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.2/YTGet-windows.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.2/YTGet-linux.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>190</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.2/YTGet-linux.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.2/YTGet-macOS-arm64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>105</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.2/YTGet-macOS-arm64.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.2/YTGet-macOS-x86_64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>110</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.2/YTGet-macOS-x86_64.7z">
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
