## ✨ What's New
# v2.7.9

This release focuses heavily on **performance, download reliability, and queue stability**, especially for large queues and long-running downloads.

### ⚡ Performance & UI

* **Much smoother download logs:** Console output is now buffered and written in batches instead of updating the UI for every individual log line. Auto-scrolling also respects your current scroll position.
* **Faster queue updates:** Rebuilding the queue now happens in a single UI update instead of repainting after every card.
* **Faster large queues:** Queue items can now be located instantly instead of searching through the entire list repeatedly. This makes a noticeable difference with large playlists.
* **Less unnecessary progress work:** The UI no longer refreshes when the download percentage hasn't changed.
* **Faster search:** Queue search now waits briefly after typing before filtering, making it much smoother.
* **Smoother queue scrolling:** Removed several sources of lag from queue cards, including unnecessary mouse-event processing and always-active shadows. Shadows are now only enabled when hovering over a card.

### 📥 More Reliable Downloads

* **Fixed “Requested format is not available”:** Preferred formats now have a fallback, so yt-dlp can automatically choose another suitable format instead of failing when a specific stream isn't available.
* **Automatic recovery from temporary download failures:** Downloads that fail because of temporary network/server problems can now automatically restart and try again.
* **Better recovery from expired download links:** Long downloads can now recover from expired video URLs by restarting yt-dlp and obtaining a fresh link.
* Added several additional reliability improvements for interrupted fragments, temporary server errors, connection problems, and timeouts.

### 🔄 Better Queue Behavior

* **Failed downloads are no longer silently removed.** After automatic retries are exhausted, failed items are moved to the end of the queue and can be retried again.
* Failed items get a limited number of additional queue retries before being marked **Error**.
* **Cancelled and stopped downloads remain visible** instead of disappearing from the queue.
* The queue now correctly skips completed, cancelled, and permanently failed items when looking for the next download.
* Overall queue progress now reflects the actual status of each item rather than relying on the queue shrinking.
* **Clear Completed** now also removes cancelled items, while failed items remain available for review.

### 📝 Download Output & Metadata

* **Fixed corrupted non-ASCII text:** Characters in titles and console output could occasionally be lost when UTF-8 data arrived in pieces. Output handling now correctly preserves characters split across data chunks.
* **Reduced UI overhead during heavy output:** Larger output chunks significantly reduce the amount of communication between the downloader and UI.
* Removed repeated work when cleaning music-video metadata, improving efficiency during completed downloads.

### 🖼️ Faster Thumbnail Loading

Thumbnail loading has been substantially optimized:

* YouTube thumbnails are now resolved directly when possible instead of launching yt-dlp for every thumbnail.
* yt-dlp is only used when the direct thumbnail lookup isn't sufficient.
* Browser cookie refreshing is no longer performed for every thumbnail request.
* Thumbnail downloads can now run concurrently using the configured number of workers.
* Duplicate thumbnail requests are avoided.
* Removed unnecessary delays between thumbnail requests.
* Thumbnail connections are reused instead of repeatedly creating new connections.

The result is significantly faster and smoother thumbnail loading, particularly for large playlists.

### 🏷️ Title Fetching

* **Fixed a queue-breaking bug:** After the title-fetch queue was stopped once, it could become permanently stuck and reject future requests. It now correctly starts processing again.
* Consolidated duplicated title-fetching logic into a shared component, reducing duplicated code and keeping both fetching paths consistent.
* Improved handling of malformed text and metadata responses.
* Added faster failure handling for stalled connections.
* Reduced unnecessary yt-dlp warning output.
* Improved environment/path handling.

---
## 🆚 Updated Dependencies
- **yt-dlp:** `2026.07.04`
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
