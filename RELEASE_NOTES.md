## ✨ What's New
# v2.7.9

> ⚠️ **Recommended after updating:** Go to **Preferences → YouTube Player Client** and set it to **`default,web_embedded`**, then click **Save**.
> yt-dlp's default `tv_downgraded` client is currently broken for many users upstream. This switches to a known-working, cookies-safe fallback without waiting for another yt-dlp update.
> 
> ⚠️ **Some formats are still limited or temporarily unavailable on YouTube itself.** These cannot be fixed by the app alone. If a specific format continues to fail, we may need to wait for an **yt-dlp update** to adapt to changes on YouTube.

## 🚀 More Reliable Downloads

* Fixed **“Requested format is not available”** errors for audio and video downloads by adding a fallback when the preferred format isn't available.
* Added automatic recovery for temporary **403, 429, 5xx, timeout, and connection errors**. Failed downloads can now retry automatically instead of stopping immediately.
* Failed items are now **moved to the end of the queue** and retried before being marked as an error.
* Stopped and skipped downloads remain visible in the queue instead of disappearing.
* Added additional yt-dlp retry and connection options to make long downloads more reliable.



## ⚡ Major Performance Improvements

* Greatly reduced console/UI stuttering during downloads by batching log output instead of updating the interface for every line.
* The console now only auto-scrolls when you're already at the bottom, so scrolling up no longer gets interrupted.
* Queue updates are now much faster, especially with large queues.
* Replaced repeated searches through the entire queue with direct lookups, making progress and thumbnail updates significantly faster for large playlists.
* Duplicate progress updates are now ignored when the percentage hasn't changed.
* Search is now debounced, reducing unnecessary work while typing.
* Reduced queue-card scrolling lag by optimizing hover effects, mouse events, and widget repaints.
* Thumbnail loading is substantially faster, especially for large playlists.

## 🖼️ Faster Thumbnail Loading

* YouTube thumbnails are now resolved directly from the video URL whenever possible instead of launching yt-dlp for every thumbnail.
* Thumbnail downloads can now run concurrently.
* Duplicate thumbnail requests are automatically avoided.
* Browser cookie refreshes are throttled instead of happening for every thumbnail.
* Reused HTTP connections to reduce overhead.
* yt-dlp is only used as a fallback when a thumbnail cannot be resolved directly.

## 📝 Title & Metadata Improvements

* Fixed an issue where the title-fetching queue could permanently stop processing after being stopped once.
* Consolidated duplicated metadata-fetching code to make it more reliable and consistent.
* Improved handling of non-ASCII characters and malformed output.
* Reduced unnecessary yt-dlp warnings and socket hangs during metadata fetching.
* Improved environment/PATH handling.

## 🔤 Fixed Garbled Characters

* Fixed non-ASCII characters occasionally being corrupted or disappearing from download output.
* UTF-8 output is now handled correctly even when a character is split across two output chunks.

## 📦 New

* **Extra yt-dlp Args** — enter additional yt-dlp arguments such as `--sleep-interval 5 --max-sleep-interval 15` and have them applied to downloads.
* **YouTube Player Client** — choose which yt-dlp YouTube extraction client to use, giving you a way to work around upstream YouTube changes.

## 🧹 Queue Improvements

* Failed items remain visible so you can review what went wrong.
* The queue progress indicator now correctly tracks completed, cancelled, and failed items.
* The queue continues processing even when an item at the front has permanently failed.


---
## 🆚 Updated Dependencies
- **yt-dlp:** `2026.08.19`
- **ffmpeg:** `9.0.1`  
- **deno:**  `2.9.5`
- **SpotDL (Windows only):**  `4.5.2 - hotfix`
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-windows.zip">
          <img src="https://img.shields.io/badge/Download-ZIP-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows ZIP Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>165</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-windows.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-linux.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>190</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-linux.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-macOS-arm64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>105</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-macOS-arm64.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-macOS-x86_64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>110</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.7.9/YTGet-macOS-x86_64.7z">
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
