# ✨ What's New v2.8.5

## Release summary

YTGet 2.8.5 is a queue-management, reliability and compatibility release. Recording types can now be changed on queued items **in place**, queue cards show the size for the **codec you actually selected**, long titles can no longer break the queue layout, and subtitle downloads that trip HTTP 429 are skipped on retries. It also fixes every known way the **yt-dlp 2026.10.26+ YouTube extractor** could fail with *"Requested format is not available"* — even though `yt-dlp -F` still listed the usual formats: an outdated bundled Deno is no longer forced onto yt-dlp, metadata fetches recover by relaxing the settings that caused the failure, downloads drop a pinned player client that yields no formats, and the queue log now shows *why* formats went missing. The recommended anti-429 **sleep pacing** now has its own section in Advanced, with a **Custom** mode that lets you dial in your own four values. The **EJS challenge-solver crash** on YouTube's late-November players is detected and reported as a yt-dlp update need instead of being retried into the ground.

All existing settings, profiles and queue files carry over unchanged.

---

## ⚡ Highlights

### 🔄 Change the recording type of queued items, in place

Select one or more rows and use the bulk bar's **TYPE** button (or right-click → **Change recording type…**) to switch them to any preset. Items keep their position, details, thumbnail and per-item options; completed items are reset to Pending so the new type downloads, and size estimates are refreshed. No more copy-the-URL, re-add, delete-the-wrong-row gymnastics.

### 🧩 Fix: "Requested format is not available" on every YouTube item

Recent yt-dlp releases changed how YouTube formats are extracted, in two ways that could leave YTGet with zero usable formats:

1. **A JS challenge runtime is now required.** yt-dlp rejects Deno older than **2.3.0** and then silently falls back to YouTube's JS-less clients — which can expose no downloadable formats at all. YTGet used to force its own bundled Deno onto every yt-dlp call, so an old bundled Deno broke every fetch.
2. **Some manually selectable player clients (android, ios) are now PO-token-gated.** A client pinned in Preferences could return no formats for every video.

What changed:

- YTGet probes the bundled Deno's version and only pins it (and only puts it on PATH) when it is **2.3.0 or newer**. Otherwise yt-dlp's own runtime discovery takes over — it will happily use a newer system Deno or Node you have installed.
- The startup banner warns when your bundled Deno is too old: **Help › Check for Updates › Deno › Update** fixes it in a few clicks.

### 🔄 Metadata fetches recover instead of retrying a doomed command

"Requested format is not available" is a configuration problem, not a rate limit — retrying the identical command for 5 minutes can never succeed. Now:

- The details fetch immediately retries **without the pinned player client** (and, if that also fails, once more **unsigned**) the moment yt-dlp reports no usable formats.
- Items whose details only resolved via the fallback automatically download with yt-dlp's default clients, so they don't hit the same wall.
- Failed downloads get the same treatment: in-app retries and queue-level retries drop the pinned client for that item.

### 🔍 The reason a failure is now visible

yt-dlp only prints *why* formats went missing (client skipped, PO token required, no JS runtime) as warnings, which the details fetch used to suppress. Warnings are now kept, and the queue log's error line includes the relevant ones — so a future YouTube-side change shows its actual cause instead of a bare "Requested format is not available".

### 💥 Detects the challenge-solver crash (update yt-dlp to 2026.11.23 or newer)

YouTube's late-November players (05a4ffc0, b485e332, b17b74e6, 92eef845) crash yt-dlp's EJS n-challenge solver with `TypeError: a.addOnDisposeCallback is not a function`, which strips every downloadable format — the item then fails with "Only images are available for download / Requested format is not available". This is an upstream bug (yt-dlp#18123, ejs#79), fixed in **yt-dlp 2026.11.23**; it is not a Deno, cookies or network problem, and no amount of retrying helps. YTGet now recognises the signature, skips its own retries for it, fails the item once with a message that says exactly what to do — **Help › Check for Updates › yt-dlp › Update** — and keeps the item in the queue for a manual retry after the update. A solver warning whose formats still download is unaffected.

### 🛠️ Preferences cleanup

The player-client list was aligned with what current yt-dlp can actually serve without a PO token:

- **android** and **ios** were removed (pinning either failed every download on every yt-dlp since 2025).
- **tv_samsung** was added (part of the extractor's current default set).
- A stored selection that is no longer offered is reset to **Auto** on load — configurations saved against the old list repair themselves silently.

### ⏱️ Request pacing: preset or custom (new in Advanced)

The recommended anti-429 spacing — `--sleep-subtitles 5 --sleep-requests 0.75 --sleep-interval 10 --max-sleep-interval 20` — previously had to be typed into the **Extra arguments** field and was lost whenever that field was cleared. It now has its own **Request pacing** card under the same tab in Advanced: pick **Sleep (gentle spacing)** and every download command is spaced out to stay under YouTube's rate limit, or pick **Custom** and dial in your own four values in spin boxes (they start from the Sleep recipe, so a fresh Custom selection matches it until you change one). The same flags typed in Extra arguments still take precedence. Off by default, because pacing slows large queues down.

### ✅ Other fixes and improvements

- Queue cards quote the size for the codec your format sort actually prefers (AV1/VP9/AVC), not always the largest stream at the target height.
- Long or unbroken titles can no longer give the queue a horizontal scrollbar and push the action buttons out of view.
- HTTP 429 on subtitles disables them for that item's retries instead of failing the whole download.
- New regression tests for the Deno version gate, the fetch fallback chain, the worker/controller player-client dropping, client-list validation, the request-pacing preset and the widened change-type dialog.
- Version metadata updated across the app, package, Windows/macOS resources and website.

---

### 📋 Notes

- If the startup banner warns about Deno, update it once via **Help › Check for Updates**; the warning disappears after the update.
- The per-item "use default clients" override only kicks in automatically after a format-selection failure; it is kept if the item is re-queued.
- Updating yt-dlp and updating Deno are separate steps on purpose — one click each in Help › Check for Updates.
- Enable the Request pacing card in **Preferences › Advanced** if you hit frequent HTTP 429 rate limits — pick **Sleep (gentle spacing)** for the recommended recipe, or **Custom** to dial in your own four values.

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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.5/YTGet-2.8.5-windows-setup.exe">
          <img src="https://img.shields.io/badge/Download-Setup-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows Installer Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>ZIP</td>
      <td><strong>255 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.5/YTGet-windows.zip">
          <img src="https://img.shields.io/badge/Download-ZIP-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows ZIP Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>165</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.5/YTGet-windows.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.5/YTGet-linux.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>190</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.5/YTGet-linux.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.5/YTGet-macOS-arm64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>105</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.5/YTGet-macOS-arm64.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.5/YTGet-macOS-x86_64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>110</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.5/YTGet-macOS-x86_64.7z">
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
