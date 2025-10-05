# File: ytget_gui/workers/title_fetcher.py

from __future__ import annotations

import json
import subprocess
import platform
import os
from pathlib import Path
from typing import Optional, List, Any

from PySide6.QtCore import QObject, Signal

from ytget_gui.settings import AppSettings
from ytget_gui.workers import cookies as CookieManager


class TitleFetcher(QObject):
    """
    Fetch basic metadata for a URL using yt-dlp.

    Signals:
      - metadata_fetched(url, title, video_id, thumbnail_url, is_playlist)
      - title_fetched(url, title)   (legacy/compat)
      - error(url, message)
      - finished()
    """

    title_fetched = Signal(str, str)                    # url, title (legacy)
    metadata_fetched = Signal(str, str, str, str, bool) # url, title, video_id, thumb_url, is_playlist
    error = Signal(str, str)                            # url, error message
    finished = Signal()

    def __init__(
        self,
        url: str,
        yt_dlp_path: Path,
        ffmpeg_dir: Path,
        cookies_path: Path,
        proxy_url: str,
        settings: Optional[AppSettings] = None,
        cookies_from_browser: Optional[str] = None,
        cookies_profile: Optional[str] = None,
    ):
        super().__init__()
        self.url = url
        self.yt_dlp_path = yt_dlp_path
        self.ffmpeg_dir = ffmpeg_dir
        self.cookies_path = cookies_path
        self.proxy_url = proxy_url
        self.settings = settings
        self.cookies_from_browser = cookies_from_browser
        self.cookies_profile = cookies_profile

    def run(self):
        try:
            # If settings request auto-refresh from browser, attempt it (best-effort)
            try:
                if self.settings is not None and getattr(self.settings, "COOKIES_AUTO_REFRESH", False) and getattr(self.settings, "COOKIES_FROM_BROWSER", ""):
                    ok, msg = CookieManager.refresh_before_download(self.settings)
                    if ok:
                        # update cookies_path in case export wrote to default
                        self.cookies_path = getattr(self.settings, "COOKIES_PATH", self.cookies_path)
                    else:
                        # surface a non-fatal warning via error signal
                        self.error.emit(self.url, f"Cookies refresh: {msg}")
            except Exception:
                pass

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

            # Cookies handling: prefer explicit cookies_from_browser param, else settings, else file cookies
            cookies_from = self.cookies_from_browser or (getattr(self.settings, "COOKIES_FROM_BROWSER", "") if self.settings is not None else "")
            if cookies_from:
                if self.cookies_profile:
                    cmd.extend(
                        [
                            "--cookies-from-browser",
                            f"{cookies_from}:{self.cookies_profile}",
                        ]
                    )
                else:
                    cmd.extend(["--cookies-from-browser", cookies_from])
            elif self.cookies_path and self.cookies_path.exists() and self.cookies_path.stat().st_size > 0:
                cmd.extend(["--cookies", str(self.cookies_path)])

            # Proxy
            if self.proxy_url:
                cmd.extend(["--proxy", self.proxy_url])

            # Prepare subprocess environment so phantomjs and bundled binaries are visible immediately
            env = os.environ.copy()
            try:
                if self.settings is not None:
                    extra_paths = []
                    extra_paths.append(str(self.settings.INTERNAL_DIR))
                    extra_paths.append(str(self.settings.BASE_DIR))
                    ph = getattr(self.settings, "PHANTOMJS_PATH", None)
                    if ph and ph.exists():
                        extra_paths.append(str(ph.parent))
                    cur_path = env.get("PATH", "")
                    for p in reversed(extra_paths):
                        if p and p not in cur_path:
                            cur_path = f"{p}{os.pathsep}{cur_path}"
                    env["PATH"] = cur_path
                    if os.name == "nt" and not env.get("PATHEXT"):
                        env["PATHEXT"] = ".COM;.EXE;.BAT;.CMD"
            except Exception:
                pass

            # Hide child console on Windows, leave None elsewhere
            startupinfo = None
            if platform.system().lower().startswith("win"):
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo = si
                except Exception:
                    startupinfo = None

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
                startupinfo=startupinfo,
                encoding="utf-8",
                env=env,
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
