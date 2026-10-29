# ✨ What's New v2.8.4

## Release summary

YTGet 2.8.4 fixes video quality selection to prioritize resolution correctly across codecs, streaming protocols, and progressive formats. It also introduces configurable video codec preferences and selection priorities, giving you more control over the quality of your downloads.

Existing profiles retain the default **Balanced + Auto** settings, and custom format selectors remain untouched.

---

## ⚡ Highlights

### 🎬 Video quality selection that works as expected

- **Fixed incorrect resolution selection.** Resolution presets now compare all eligible video codecs and protocols together. A lower-resolution AV1 or VP9 stream can no longer hide a higher-resolution AVC stream.
- **Resolution comes first.** Video formats are ranked explicitly by resolution, frame rate, and reported video bitrate, according to your selected priority. Codec, protocol, and extractor preferences no longer override these criteria.
- **HLS is supported in normal presets.** HLS formats are no longer excluded from standard quality selections. Availability depends on the video, player client, and session.
- **Progressive formats are included.** Higher-resolution streams that already contain both video and audio can now compete fairly against separate video streams.
- **Resolution limits are respected.** Height limits and Universal preset width limits are preserved across all built-in selection branches.
- **WebM compatibility is improved.** Built-in WebM presets now restrict video and audio codecs to WebM-compatible formats, avoiding remux failures caused by incompatible combinations such as AVC/AAC. WebM may offer fewer resolution choices than MKV; choose MKV for unrestricted codec and protocol selection.

### 🎛️ New: Video quality preferences

Find the new settings under **Preferences → Output → Video quality**.

#### Preferred codec

Choose your preferred video codec:

- **Auto** — Allow any codec.
- **AV1** — Prefer AV1 video.
- **VP9** — Prefer VP9 video.
- **H.264 / AVC** — Prefer H.264 video.

Codec preference is a selection preference, not a transcoding option. YTGet selects existing streams rather than converting videos to another codec.

#### Selection priority

Choose how eligible video formats are ranked:

- **Balanced (default):** Resolution → Frame rate → Reported video bitrate.
- **Highest video bitrate:** Resolution → Reported video bitrate → Frame rate.
- **Preferred codec first:** Resolution → Preferred codec → Frame rate → Reported video bitrate.

Resolution remains the primary criterion in every mode. A higher-resolution eligible stream can therefore beat a lower-resolution stream using your preferred codec.

In **Balanced** and **Highest video bitrate** modes, the preferred codec acts only as a tie-breaker after the mode's primary ranking criteria. With **Auto + Preferred codec first**, yt-dlp's normal codec ranking is used within the best eligible resolution.

#### Compatibility and saved settings

- Choose the resolution cap in the main window as before.
- If your preferred codec is unavailable, selection falls back automatically.
- Selecting H.264 with the WebM container uses Auto codec ranking and displays an explanation. Choose MKV or MP4 to prefer H.264.
- Settings are saved with the profile and apply to downloads started afterward, including pending queue items. Running downloads are not reconfigured.
- Manual format IDs, custom selectors, and advanced yt-dlp overrides remain available.
- Existing profiles retain the **Balanced + Auto** defaults.

### 🛠️ Other fixes and improvements

- **Old queue entries migrate correctly.** Previously saved built-in selectors are migrated to the new selectors when restored. The worker also normalizes old selectors before downloading, and queue keys and duplicate detection use the migrated representation. Custom selectors remain unchanged.
- **Consistent cookie handling.** Metadata fetching and downloading now follow the same cookie-file-first policy unless a metadata request explicitly specifies a browser or profile override.
- **Deno configuration is respected.** Metadata fetching now receives the configured Deno path, just like downloads.
- **Safer queue restoration.** Persisted file sizes containing NaN or infinity no longer crash queue restoration.
- **More accurate preset size reporting.** A preset no longer advertises a file size above the configured resolution cap when no matching height exists.

---

### 📋 Notes


- Custom selectors and explicit format IDs are not rewritten.
- Built-in WebM presets prioritize compatibility, while MKV allows unrestricted codec and protocol selection.
- Preferred codec settings do not guarantee that a particular codec or resolution will be available for every video.
- Downloaded video quality depends on the formats actually offered by YouTube and the selection rules configured in YTGet.


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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.4/YTGet-2.8.4-windows-setup.exe">
          <img src="https://img.shields.io/badge/Download-Setup-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows Installer Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>ZIP</td>
      <td><strong>255 MB</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.4/YTGet-windows.zip">
          <img src="https://img.shields.io/badge/Download-ZIP-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows ZIP Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>165</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.4/YTGet-windows.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.4/YTGet-linux.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-FCC624?style=flat-square&logo=linux&logoColor=black" alt="Linux tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>190</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.4/YTGet-linux.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.4/YTGet-macOS-arm64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-000000?style=flat-square&logo=apple&logoColor=white" alt="macOS ARM tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>105</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.4/YTGet-macOS-arm64.7z">
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
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.4/YTGet-macOS-x86_64.tar.gz">
          <img src="https://img.shields.io/badge/Download-tar.gz-555555?style=flat-square&logo=apple&logoColor=white" alt="macOS Intel tar.gz Download">
        </a>
      </td>
    </tr>
    <tr>
      <td>7z</td>
      <td><strong>110</strong></td>
      <td>
        <a href="https://github.com/ErfanNamira/ytget-gui/releases/download/2.8.4/YTGet-macOS-x86_64.7z">
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