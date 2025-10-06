## ✨ What’s New

🍪 **Smart Cookie Management & Auto Refresh**  
   - Introduced a **dynamic cookie system** that automatically imports and prunes browser cookies for optimal reliability.  
   - Integrated **automatic cookie refresh** into title fetching, metadata retrieval, and download workers — no more repeated manual exports.  
   - Fixed issues with large cookie headers (HTTP 413 errors) and improved the overall import/export user experience.  

🕒 **Persistent Cookie Preferences**  
   - Cookie-related preferences are now **saved instantly** when changed in the Preferences dialog.  
   - Added a **“Last Imported” timestamp** marker whenever cookies are exported from a browser.  
   - All workers that handle cookies now **sync changes to AppSettings** and persist them automatically for a smoother experience.  

⚙️ **Console Log Optimization**  
   - Added a hard limit of **200 log lines** to keep memory usage low and the UI snappy.  
   - Improved performance by appending logs directly when viewing “All,” reducing unnecessary re-renders.  
   - Old log entries are trimmed automatically to prevent unbounded growth.  

---

## 🛠️ Fixes & Improvements

- Improved synchronization between workers and cookie storage.  
- Reduced memory use and improved UI responsiveness during long sessions.  
- Safer cookie exports and cleaner import logic for various browsers.  
- Enhanced app stability and reduced redundant refresh operations.  

---

## 📥 Downloads

#### 🪟 Windows · x86_64 · 150 MB  
[⬇ Download for Windows](https://github.com/ErfanNamira/ytget-gui/releases/download/2.5.1/YTGet-windows.zip)

#### 🐧 Linux · x86_64 · 180 MB  
[⬇ Download for Linux](https://github.com/ErfanNamira/ytget-gui/releases/download/2.5.1/YTGet-linux.tar.gz)

#### 🍎 macOS (ARM) · arm64 · 100 MB  
[⬇ Download for macOS ARM](https://github.com/ErfanNamira/ytget-gui/releases/download/2.5.1/YTGet-macOS-arm64.tar.gz)

#### 🍎 macOS (Intel) · x86_64 · 100 MB  
[⬇ Download for macOS Intel](https://github.com/ErfanNamira/ytget-gui/releases/download/2.5.1/YTGet-macOS-x86_64.tar.gz)

---

### 🆚 Updated Dependencies
- **yt-dlp:** `2025.09.26`  
- **ffmpeg:** `8.0.0`  

---

### 📊 VirusTotal Scan
🔗 [View scan results on VirusTotal](https://www.virustotal.com)  

_The archive contains `.exe` files, which may still occasionally be flagged by some antivirus engines as **false positives**. These are not actual threats._  
