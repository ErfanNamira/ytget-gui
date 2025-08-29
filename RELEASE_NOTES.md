## ✨ What’s New

1. **Cross-Platform Release**  
   - Fully tested on **Windows**, **macOS**, and **Linux**.  
   - Unified code paths and asset handling across all supported operating systems.  

2. **Enhanced Save Keybindings**  
   - All dialogs now accept **Ctrl + Enter** (Windows/Linux) and **⌘ + Enter** (macOS) to save or accept.  

3. **Full Thread‐Safety Overhaul**  
   - Every signal from worker threads into the UI now uses `Qt.QueuedConnection`.  
   - Eliminated the “Cannot create children for a parent in a different thread” Qt error.  

4. **Post-Queue Action Refinement**  
   - The **Keep** action is now a silent no-op (no warning).  
   - Shutdown, Sleep, Restart and Close are dispatched through the GUI thread to guarantee correct behavior.  

5. **UpdateManager Improvements**  
   - Unified OS detection via `platform.system()`.  
   - Broader macOS asset matching (Intel and Universal2 binaries).  
   - Graceful fallback around `CREATE_NO_WINDOW` on non-Windows Python builds.  

6. **YouTube URL Validator Extended**  
   - Now matches `youtube-nocookie.com` URLs.  
   - Strips trailing slashes before validation for more forgiving input.  

7. **Thumbnail Fetcher Optimized**  
   - Reuses a single `requests.Session` (with optional proxy).  
   - Retries each URL up to 3 times with exponential backoff.  
   - Filters out tiny placeholder images (< 1 KiB).  
   - Writes atomically via a temp file, then renames into place.  

8. **Styles & High-DPI Support**  
   - Enabled `Qt.AA_EnableHighDpiScaling` and `Qt.AA_UseHighDpiPixmaps`.  
   - Dynamically scales fonts, padding and radii based on the screen’s DPI.    

---

### 🆚 Updated Dependencies
- **yt-dlp:** `2025.08.27`  
- **ffmpeg:** `8.0.0`  

---

### 🔒 Security & False Positive Note
- **No UPX compression** – `.exe` files are now distributed **without UPX packing**, which previously triggered false positives in some antivirus software.  
- ⚠️ **Note:** This makes the package size larger, but it’s the only reliable way to avoid misleading Trojan/virus warnings.  

---

### 📊 VirusTotal Scan
[🔗 View scan results on VirusTotal](https://www.virustotal.com)  

_The archive contains `.exe` files, which may still occasionally be flagged by certain antivirus engines as **false positives**. These are not actual threats._