# File: ytget_gui/workers/title_fetcher.py
from __future__ import annotations

import json
import subprocess
import platform
from pathlib import Path
from typing import Optional, List, Any

from PySide6.QtCore import QObject, Signal


class TitleFetcher(QObject):
    """
    Fetch basic metadata for a YouTube URL using yt-dlp.

    Signals:
      - metadata_fetched(url, title, video_id, thumbnail_url, is_playlist)
      - title_fetched(url, title)   (legacy/compat)
      - error(url, message)
      - finished()
    """

    # url, title (legacy)
    title_fetched = Signal(str, str)
    # url, title, video_id, thumb_url, is_playlist
    metadata_fetched = Signal(str, str, str, str, bool)
    # url, error message
    error = Signal(str, str)
    finished = Signal()

    def __init__(
        self,
        url: str,
        yt_dlp_path: Path,
        ffmpeg_dir: Path,
        cookies_path: Path,
        proxy_url: str,
        cookies_from_browser: Optional[str] = None,  # e.g., "chrome", "firefox", "edge", "brave"
        cookies_profile: Optional[str] = None,       # e.g., "Default", "default-release"
    ):
        super().__init__()
        self.url = url
        self.yt_dlp_path = yt_dlp_path
        self.ffmpeg_dir = ffmpeg_dir
        self.cookies_path = cookies_path
        self.proxy_url = proxy_url
        self.cookies_from_browser = cookies_from_browser
        self.cookies_profile = cookies_profile

    def run(self):
        try:
            # Build yt-dlp command.
            cmd: List[str] = [
                str(self.yt_dlp_path),
                "--ffmpeg-location",
                str(self.ffmpeg_dir),
                "--skip-download",
                "--print-json",
                "--ignore-errors",
                "--flat-playlist",
                self.url,
            ]

            # Cookies handling: prefer --cookies-from-browser if provided, else file cookies
            if self.cookies_from_browser:
                if self.cookies_profile:
                    cmd.extend(
                        [
                            "--cookies-from-browser",
                            f"{self.cookies_from_browser}:{self.cookies_profile}",
                        ]
                    )
                else:
                    cmd.extend(["--cookies-from-browser", self.cookies_from_browser])
            elif self.cookies_path and self.cookies_path.exists() and self.cookies_path.stat().st_size > 0:
                cmd.extend(["--cookies", str(self.cookies_path)])

            # Proxy
            if self.proxy_url:
                cmd.extend(["--proxy", self.proxy_url])

            # Hide child console on Windows, leave None elsewhere
            startupinfo = None
            if platform.system().lower().startswith("win"):
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo = si
                except Exception:        

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
                startupinfo=startupinfo,
                encoding="utf-8",
            )

            if proc.returncode != 0:
                msg = (proc.stderr or "yt-dlp returned an error").strip()
                self.error.emit(self.url, msg)
                self.finished.emit()
                return

            output = (proc.stdout or "").strip()
            if not output:
                self.error.emit(self.url, "No metadata received from yt-dlp")
                self.finished.emit()
                return

            # yt-dlp can emit multiple JSON lines (especially for playlists).
            # Parse all valid JSON objects, in order.
            infos: List[dict[str, Any]] = []
            for line in (l for l in output.splitlines() if l.strip()):
                try:
                    infos.append(json.loads(line))
                except json.JSONDecodeError:
                    # Skip malformed lines; continue
                    continue

            if not infos:
                self.error.emit(self.url, "Failed to parse metadata: no valid JSON objects")
                self.finished.emit()
                return

            # Determine playlist context if any line indicates it
            is_playlist = any(
                ("entries" in info) or ("playlist_index" in info) or ("playlist_title" in info)
                for info in infos
            )

            # Prefer a line that contains playlist_title to derive the queue title in playlist context
            playlist_title = None
            for info in infos:
                pt = info.get("playlist_title")
                if pt:
                    playlist_title = pt
                    break

            # Use the first parsed object as the representative entry for id/thumbnail
            representative = infos[0]
            video_id = representative.get("id") or ""
            thumb_url = representative.get("thumbnail") or ""

            # Title selection: show playlist title when in playlist context; otherwise entry title
            if is_playlist and playlist_title:
                title = playlist_title
            else:
                title = representative.get("title") or "Unknown Title"

            # Emit richer metadata first
            self.metadata_fetched.emit(self.url, title, video_id, thumb_url, is_playlist)
            # Emit legacy title signal for backward compatibility
            self.title_fetched.emit(self.url, title)

        except subprocess.TimeoutExpired:
            self.error.emit(self.url, "Timeout while fetching metadata (120 seconds)")
        except Exception as e:
            self.error.emit(self.url, f"Unexpected error: {e}")
        finally:
            self.finished.emit()