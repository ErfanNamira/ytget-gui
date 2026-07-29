## ✨ What's New
- **🔑 Custom CA certificate support** for local MITM/domain-fronting proxies (e.g. [MITM-DomainFronting](https://github.com/patterniha/MITM-DomainFronting)). A new `Custom CA certificate` field in **Preferences → Network** lets you point at a self-signed cert (e.g. `mycert.crt`) so TLS validation keeps working against that specific certificate instead of being disabled outright.

### 🛠️ Fixed
- **Thumbnail downloads ignored the "Ignore SSL certificate errors" setting entirely.** `ThumbFetcher._download_with_requests()` never passed `verify=` to `requests.get()`, so it always enforced full certificate validation regardless of the toggle — this is what made SSL bypass appear broken when using a MITM-style local proxy for thumbnails specifically.
- `title_fetch_manager.py`'s metadata-fetch queue had **no SSL handling at all** (no `--no-check-certificates`, no custom CA support), unlike its sibling `title_fetcher.py`. Both now behave identically.
- SSL/CA behavior was previously inconsistent across `download_worker.py`, `title_fetcher.py`, `title_fetch_manager.py`, and `thumb_fetcher.py` — some only patched the yt-dlp subprocess flags, others missed it entirely. All four now resolve SSL/CA config through the same `ssl_utils.resolve_ssl_config()` helper.

### ⚙️ Changed
- When a custom CA cert is configured, it's now propagated to yt-dlp/ffmpeg subprocesses via `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, and `CURL_CA_BUNDLE` environment variables, so nested TLS stacks (Python's `ssl`, `requests`/`urllib3`, libcurl-linked tools) all trust it consistently — not just the in-process `requests` calls.
- `IGNORE_SSL_ERRORS` (blanket bypass) is now treated as a fallback, only applied when no valid `CUSTOM_CA_CERT` is set. Configuring a custom CA is the preferred, safer path since it keeps real certificate validation active.

### 📝 Notes
- If you use a `socks5://` proxy URL (e.g. `socks5://127.0.0.1:10808` for a local v2rayN-based MITM proxy), make sure `requests[socks]` (the `pysocks` extra) is installed, or thumbnail fetching will raise a proxy error.

---
## 🆚 Updated Dependencies
- **yt-dlp:** `2026.07.04`
- **ffmpeg:** `8.1.2`  
- **deno:**  `2.9.4`
- **SpotDL (Windows only):**  `4.5.2`
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
