# File: ytget_gui/workers/title_fetcher.py

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from ytget_gui.settings import AppSettings
from ytget_gui.workers import fetch_core


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
    metadata_fetched = Signal(str, str, str, str, bool)  # url, title, video_id, thumb_url, is_playlist
    error = Signal(str, str)                             # url, error message
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
            if fetch_core.is_spotify_url(self.url):
                title = fetch_core.spotify_placeholder_title(self.url)
                self.metadata_fetched.emit(self.url, title, "", "", False)
                self.title_fetched.emit(self.url, title)
                return

            metadata, err, updated_cookies_path, refresh_warning = fetch_core.fetch_metadata(
                url=self.url,
                yt_dlp_path=self.yt_dlp_path,
                ffmpeg_dir=self.ffmpeg_dir,
                cookies_path=self.cookies_path,
                proxy_url=self.proxy_url,
                settings=self.settings,
                cookies_from_browser=self.cookies_from_browser or "",
                cookies_profile=self.cookies_profile or "",
            )

            if updated_cookies_path is not None:
                self.cookies_path = updated_cookies_path
            if refresh_warning:
                self.error.emit(self.url, refresh_warning)

            if err is not None:
                self.error.emit(self.url, err)
                return

            self.metadata_fetched.emit(
                self.url, metadata.title, metadata.video_id, metadata.thumb_url, metadata.is_playlist
            )
            self.title_fetched.emit(self.url, metadata.title)

        except Exception as e:
            # Safety net - fetch_core.fetch_metadata already catches its own
            # subprocess errors, but this guards against anything unexpected
            # (e.g. Qt signal errors) so `finished` is always emitted.
            self.error.emit(self.url, f"Unexpected error: {e}")
        finally:
            self.finished.emit()
