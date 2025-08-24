## ✨ What’s New

1. **New `update_manager` Module**  
   - Effortlessly keep **YTGet** and its dependencies up-to-date.  
   - Checks for the latest YTGet release directly from GitHub.  
   - **yt-dlp Dependency Updates**  
     - Verifies the installed `yt-dlp` binary version.  
     - Automatically downloads and replaces it with the latest release from the official repository when needed.  

2. **Fixed "Unknown - …" Filenames**  
   - The `_build_command()` logic previously applied the `YT_MUSIC_METADATA` filename template even for non-audio jobs.  
   - This caused incorrect titles like `"Unknown - …"` in `.mkv` files.  
   - Now, filename templates apply correctly based on job type — no more bleed-through into video downloads.  

3. **Built with GitHub Actions**  
   - YTGet is now fully built and released using **GitHub Actions** for a more reliable and automated build process.  

---

### 🆚 Updated Dependencies
- **yt-dlp:** `2025.08.22`  
- **ffmpeg:** `8.0.0`  

---

### 🔒 Security & False Positive Note
- **No UPX compression** – `.exe` files are now distributed **without UPX packing**, which previously triggered false positives in some antivirus software.  
- ⚠️ **Note:** This makes the package size larger, but it’s the only reliable way to avoid misleading Trojan/virus warnings.  

---

### 📊 VirusTotal Scan
[🔗 View scan results on VirusTotal](https://www.virustotal.com)  

_The archive contains `.exe` files, which may still occasionally be flagged by certain antivirus engines as **false positives**. These are not actual threats._  
