# ✨ What's New v2.8.0

## Release summary

YTGet 2.8.0 is about leaving the app running and letting it work on its own.
It adds a full system tray presence, an automatic clipboard watcher that queues
links as you copy them, a scheduler that starts and stops the queue at set
times with its own shutdown/sleep manager, an optional run-at-login entry that
starts minimised to the tray, and plain-text link import/export for moving
batches of links in and out of the queue.

---

## ⚡ Highlights

### 🖱️ A real system tray presence

- A tray icon built from the app icon, with a live status line in its tooltip.
- Control the queue without the window: start, pause, skip, stop, clear
  finished, open the download folder, open Preferences, and Exit.
- Toggle the clipboard watcher and pick the "When the queue finishes" action
  straight from the tray menu.
- Optional minimise-to-tray and close-to-tray, so closing the window keeps
  YTGet running in the background. Only the tray's Exit action really quits.
- Left-, double-, or middle-click the icon to show or hide the window.
- Optional balloon notifications for queue, watcher, and scheduler events.
- The chosen post-queue action is remembered between launches instead of
  resetting to Keep.
- Everything above is configurable on the new **Preferences → Tray** page.
- On desktops without a tray host, the icon is skipped and the window keeps
  working exactly as before.

### 📋 A clipboard watcher that fills the queue for you

- Copy a link anywhere and YTGet queues it automatically.
- 40 popular yt-dlp-supported sites are recognised, including YouTube, YouTube
  Music, Spotify, SoundCloud, Bandcamp, Vimeo, Twitch, TikTok, Instagram,
  Facebook, X/Twitter, Reddit, Bilibili, Niconico, Odysee, Rumble, Kick, VK,
  Crunchyroll, and Archive.org.
- Matching is done on the real host, so a link that merely mentions
  `youtube.com` inside a query string is not misread.
- Per-category default formats: one preset for YouTube, one for YouTube Music,
  one for Spotify, and one for everything else. Leave a category empty to keep
  using the main window's format box.
- Optional site allowlist, so only the sites you tick are captured.
- Options for poll interval, auto-starting the queue on capture, skipping
  playlists, ignoring duplicates, and notifications, on the new
  **Preferences → Watcher** page.
- Captures are de-duplicated and capped at 25 links per clipboard change, so a
  copied wall of text cannot flood the queue.
- **Tools → Clipboard Watcher** (Ctrl+Shift+V) toggles it; **Queue Clipboard
  Now** does a single capture without leaving the watcher on.

### ⏰ A scheduler with a shutdown/sleep manager

- Start the queue at a set time and stop it at a set time, each independently
  toggleable, on the new **Preferences → Scheduler** page.
- Runs daily, or only on the weekdays you tick.
- A separate power manager runs **Shutdown**, **Sleep**, **Restart**, or
  **Close** at its own time. This deliberately takes priority over an
  unfinished queue: downloads are stopped first, then the action runs.
- Any pending post-queue action is cleared when a scheduled power action fires,
  so the machine never receives two conflicting power commands.
- Each event fires at most once per day, with a short catch-up window so a
  briefly suspended machine still triggers. Enabling the scheduler after an
  event's time has passed will not immediately run it.

### 🚀 Run at login, minimised to the tray

- Optionally launch YTGet when you sign in, straight into the tray.
- Configurable delay before starting (default 30 seconds) so the network and
  the tray host are ready.
- Implemented natively per platform: the Windows `HKCU` Run key, a macOS
  LaunchAgent, or a Linux XDG autostart entry. Preferences shows the exact path
  in use.
- New `--minimized` and `--delay SECONDS` command line flags for the same
  behaviour by hand.

### 📄 Import and export links as plain text

- **File → Import Links from Text File…** (Ctrl+I) reads one link per line and
  opens a review dialog before anything is queued.
- Choose a format per link, or set one format for every link with **Apply to
  all**. Untick any line you do not want.
- Links already in the queue are shown but unticked, duplicates are collapsed,
  and blank lines and `#` comments are ignored. Bare `www.` lines are accepted.
- Lines that are not links are counted and reported instead of disappearing
  silently.
- **File → Export Links to Text File…** (Ctrl+E) writes the whole queue, the
  current selection, or only the waiting, finished, or failed items.
- Optionally write the format after each link as `url | Format`, which the
  importer reads back, so exported files round-trip with their formats.

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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.0/YTGet-windows.zip">
          <img src="https://img.shields.io/badge/Download-ZIP-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows ZIP Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>165</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.0/YTGet-windows.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.0/YTGet-linux.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>190</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.0/YTGet-linux.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.0/YTGet-macOS-arm64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>105</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.0/YTGet-macOS-arm64.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.0/YTGet-macOS-x86_64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>110</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.0/YTGet-macOS-x86_64.7z">
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
