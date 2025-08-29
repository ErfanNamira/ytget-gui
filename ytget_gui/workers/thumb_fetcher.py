# File: ytget_gui/workers/thumb_fetcher.py
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import List, Optional

import requests
from PySide6.QtCore import QObject, Signal


class ThumbFetcher(QObject):
    """
    Downloads a YouTube thumbnail image, trying multiple standard resolutions.
    Respects an optional proxy and will retry on transient errors with backoff.
    Emits:
      - finished(video_id: str, dest_path: str)
      - error(video_id: str, message: str)
    """

    finished = Signal(str, str)
    error = Signal(str, str)

    # Candidate filename suffixes to try (JPEG first, then WEBP)
    _SUFFIXES: ClassVar[List[str]] = [
        "maxresdefault.jpg", "hqdefault.jpg", "mqdefault.jpg", "sddefault.jpg",
        "maxresdefault.webp", "hqdefault.webp",
    ]
    _MIN_ACCEPTED_SIZE = 1_024     # bytes
    _MAX_RETRIES = 3
    _BACKOFF_BASE = 0.5            # seconds

    def __init__(
        self,
        video_id: str,
        url: str,
        dest_path: Path,
        proxy_url: str = "",
        timeout: int = 10,
    ):
        super().__init__()
        self.video_id = video_id.strip()
        self.url = url.strip()
        self.dest_path = dest_path
        self.timeout = timeout
        self.session = requests.Session()

        if proxy_url:
            self.session.proxies.update({
                "http": proxy_url,
                "https": proxy_url,
            })

        # YouTube referer and common browser UA for better cache hits
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/114.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.youtube.com/",
            "Accept": "image/*;q=0.8,*/*;q=0.5",
        })

    def run(self):
        try:
            # Build URL list: explicit override first, then standard patterns
            candidates = []
            if self.url:
                candidates.append(self.url)
            if self.video_id:
                base = f"https://i.ytimg.com/vi/{self.video_id}"
                candidates.extend(f"{base}/{suffix}" for suffix in self._SUFFIXES)

            content = None
            last_error: Optional[Exception] = None

            for img_url in candidates:
                for attempt in range(1, self._MAX_RETRIES + 1):
                    try:
                        resp = self.session.get(
                            img_url,
                            timeout=self.timeout,
                            allow_redirects=True,
                        )
                        resp.raise_for_status()
                        data = resp.content
                        # reject very small placeholder images
                        if len(data) >= self._MIN_ACCEPTED_SIZE:
                            content = data
                            break
                    except Exception as exc:
                        last_error = exc
                        # exponential backoff
                        time.sleep(self._BACKOFF_BASE * attempt)
                        continue
                if content:
                    break

            if content is None:
                raise last_error or RuntimeError("No thumbnail succeeded")

            # Ensure parent directory exists
            self.dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Write to a temporary file, then atomically rename
            tmp = Path(tempfile.NamedTemporaryFile(
                delete=False,
                suffix=self.dest_path.suffix or ".jpg"
            ).name)
            tmp.write_bytes(content)
            tmp.replace(self.dest_path)

            self.finished.emit(self.video_id, str(self.dest_path))

        except Exception as exc:
            msg = str(exc) or "Unknown error fetching thumbnail"
            self.error.emit(self.video_id, msg)