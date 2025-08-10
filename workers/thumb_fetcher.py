# File: ytget/workers/thumb_fetcher.py
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import requests
from PySide6.QtCore import QObject, Signal


class ThumbFetcher(QObject):
    finished = Signal(str, str)  # video_id, dest_path
    error = Signal(str, str)     # video_id, message

    def __init__(
        self,
        video_id: str,
        url: str,
        dest_path: Path,
        proxy_url: str = "",
        timeout: int = 10,
    ):
        super().__init__()
        self.video_id = video_id
        self.url = url
        self.dest_path = dest_path
        self.proxy_url = proxy_url
        self.timeout = timeout

    def run(self):
        try:
            proxies = {"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36 OPR/90.0.0.0",
                "Accept": "image/avif,image/webp,image/apng,image/*;q=0.8,*/*;q=0.5",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.youtube.com/",
            }

            # Build candidate URLs: prefer provided URL, then common YouTube patterns
            urls: List[str] = []
            if self.url:
                urls.append(self.url)

            if self.video_id:
                base = f"https://i.ytimg.com/vi/{self.video_id}"
                # JPEG variants (most widely supported)
                urls.extend(
                    [
                        f"{base}/maxresdefault.jpg",
                        f"{base}/hqdefault.jpg",
                        f"{base}/mqdefault.jpg",
                        f"{base}/sddefault.jpg",
                    ]
                )
                # WEBP variants (good quality, often available)
                urls.extend(
                    [
                        f"{base}/maxresdefault.webp",
                        f"{base}/hqdefault.webp",
                    ]
                )

            content: Optional[bytes] = None
            last_err: Optional[Exception] = None

            for u in urls:
                try:
                    r = requests.get(
                        u,
                        timeout=self.timeout,
                        proxies=proxies,
                        headers=headers,
                        allow_redirects=True,
                    )
                    r.raise_for_status()
                    # Filter out tiny "not found" placeholders; accept > 1KB
                    if len(r.content) > 1024:
                        content = r.content
                        break
                except Exception as e:
                    last_err = e
                    continue

            if content is None:
                raise last_err or RuntimeError("No thumbnail URL succeeded")

            self.dest_path.parent.mkdir(parents=True, exist_ok=True)
            # Write atomically via .part and then move into place
            tmp = (
                self.dest_path.with_suffix(self.dest_path.suffix + ".part")
                if self.dest_path.suffix
                else self.dest_path.with_suffix(".part")
            )
            with open(tmp, "wb") as f:
                f.write(content)
            tmp.replace(self.dest_path)

            self.finished.emit(self.video_id, str(self.dest_path))
        except Exception as e:
            self.error.emit(self.video_id, str(e))
