# File: ytget_gui/workers/title_fetcher.py
"""One-shot metadata fetch for a single URL."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from ytget_gui.workers import fetch_core


class TitleFetcher(QObject):
    """Signals mirror TitleFetchQueue so either can drive the same UI slots."""

    metadata_fetched = Signal(str, str, str, str, bool)
    title_fetched = Signal(str, str)
    error = Signal(str, str)
    finished = Signal()

    def __init__(
        self,
        url: str,
        yt_dlp_path: Path,
        ffmpeg_dir: Path,
        cookies_path: Optional[Path],
        proxy_url: str,
        settings=None,
        cookies_from_browser: str = "",
        cookies_profile: str = "",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.yt_dlp_path = yt_dlp_path
        self.ffmpeg_dir = ffmpeg_dir
        self.cookies_path = cookies_path
        self.proxy_url = proxy_url
        self.settings = settings
        self.cookies_from_browser = cookies_from_browser
        self.cookies_profile = cookies_profile

    def run(self) -> None:
        try:
            result = fetch_core.fetch_metadata(
                url=self.url,
                yt_dlp_path=self.yt_dlp_path,
                ffmpeg_dir=self.ffmpeg_dir,
                cookies_path=self.cookies_path,
                proxy_url=self.proxy_url,
                settings=self.settings,
                cookies_from_browser=self.cookies_from_browser,
                cookies_profile=self.cookies_profile,
            )

            if result.cookies_path is not None:
                self.cookies_path = result.cookies_path
            if result.warning:
                self.error.emit(self.url, result.warning)

            if not result.ok:
                if not result.cancelled:
                    self.error.emit(self.url, result.error or "Unknown error")
                return

            md = result.metadata
            self.metadata_fetched.emit(
                self.url, md.title, md.video_id, md.thumb_url, md.is_playlist
            )
            self.title_fetched.emit(self.url, md.title)
        except Exception as exc:  # noqa: BLE001 - guarantee `finished` fires
            self.error.emit(self.url, f"Unexpected error: {exc}")
        finally:
            self.finished.emit()
