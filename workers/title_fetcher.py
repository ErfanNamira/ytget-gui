# File: ytget/workers/title_fetcher.py
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, Signal

class TitleFetcher(QObject):
    title_fetched = Signal(str, str)   # url, title
    error = Signal(str, str)           # url, error message
    finished = Signal()

    def __init__(self, url: str, yt_dlp_path: Path, ffmpeg_dir: Path, cookies_path: Path, proxy_url: str):
        super().__init__()
        self.url = url
        self.yt_dlp_path = yt_dlp_path
        self.ffmpeg_dir = ffmpeg_dir
        self.cookies_path = cookies_path
        self.proxy_url = proxy_url

    def run(self):
        try:
            cmd = [
                str(self.yt_dlp_path),
                "--ffmpeg-location", str(self.ffmpeg_dir),
                "--skip-download",
                "--print-json",
                "--ignore-errors",
                "--flat-playlist",
                self.url,
            ]
            if self.cookies_path.exists() and self.cookies_path.stat().st_size > 0:
                cmd.extend(["--cookies", str(self.cookies_path)])
            if self.proxy_url:
                cmd.extend(["--proxy", self.proxy_url])

            startupinfo = None
            if subprocess._mswindows:  # type: ignore[attr-defined]
                si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
                startupinfo = si

            proc = subprocess.run(
                cmd, capture_output=True, text=True, check=False, timeout=120, startupinfo=startupinfo, encoding="utf-8"
            )
            if proc.returncode != 0:
                self.error.emit(self.url, (proc.stderr or "yt-dlp returned an error").strip())
                self.finished.emit()
                return

            output = proc.stdout.strip()
            if not output:
                self.error.emit(self.url, "No metadata received from yt-dlp")
                self.finished.emit()
                return

            first_line = output.splitlines()[0]
            info = json.loads(first_line)
            title = info.get("playlist_title") or info.get("title") or "Unknown Title"
            if "playlist_title" in info:
                title = f"{title} [Playlist]"

            self.title_fetched.emit(self.url, title)
        except subprocess.TimeoutExpired:
            self.error.emit(self.url, "Timeout while fetching metadata (120 seconds)")
        except json.JSONDecodeError as e:
            self.error.emit(self.url, f"Failed to parse metadata: {e}")
        except Exception as e:
            self.error.emit(self.url, f"Unexpected error: {e}")
        finally:
            self.finished.emit()