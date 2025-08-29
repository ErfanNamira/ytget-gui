# File: ytget_gui/workers/title_fetch_manager.py
from __future__ import annotations

import json
import subprocess
from typing import List, Any, Deque, Set, Optional
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ytget_gui.settings import AppSettings


class TitleFetchQueue(QObject):
    """
    Serial queue that fetches titles one-by-one in its own thread.
    Signals are forwarded to UI just like TitleFetcher did.
    """

    # Forwarded signals
    metadata_fetched = Signal(str, str, str, str, bool)   # url, title, video_id, thumb_url, is_playlist
    title_fetched = Signal(str, str)                      # url, title (legacy)
    error = Signal(str, str)                              # url, message

    # Optional signals for status/UX
    started_one = Signal(str)     # url
    finished_one = Signal(str)    # url
    idle = Signal()

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self._queue: Deque[str] = deque()
        self._pending: Set[str] = set()
        self._running = False
        self._stopping = False

    @Slot(str)
    def enqueue(self, url: str):
        if not url or url in self._pending:
            return
        self._queue.append(url)
        self._pending.add(url)
        if not self._running:
            self._process_next()

    @Slot(list)
    def enqueue_many(self, urls: List[str]):
        added = False
        for u in urls:
            if u and u not in self._pending:
                self._queue.append(u)
                self._pending.add(u)
                added = True
        if added and not self._running:
            self._process_next()

    @Slot()
    def stop(self):
        # Soft stop: finish current item and drain nothing else
        self._stopping = True

    def _process_next(self):
        if self._stopping:
            self._queue.clear()
            self._pending.clear()
            self._running = False
            self.idle.emit()
            return

        if not self._queue:
            self._running = False
            self.idle.emit()
            return

        url = self._queue.popleft()
        self._running = True
        self.started_one.emit(url)

        try:
            self._fetch_one(url)
        finally:
            self._pending.discard(url)
            self.finished_one.emit(url)
            # Continue with next
            self._process_next()

    def _fetch_one(self, url: str):
        """
        Inline version of TitleFetcher.run(), but without extra per-job QThread.
        Runs in this worker thread. Emits the same signals expected by MainWindow.
        """
        yt_dlp_path: Path = self.settings.YT_DLP_PATH
        ffmpeg_dir: Path = self.settings.FFMPEG_PATH.parent
        cookies_path: Path = self.settings.COOKIES_PATH
        proxy_url: str = self.settings.PROXY_URL or ""

        cmd: List[str] = [
            str(yt_dlp_path),
            "--ffmpeg-location", str(ffmpeg_dir),
            "--skip-download",
            "--print-json",
            "--ignore-errors",
            "--flat-playlist",
            url,
        ]

        # Cookies
        if cookies_path and cookies_path.exists() and cookies_path.stat().st_size > 0:
            cmd.extend(["--cookies", str(cookies_path)])

        # Proxy
        if proxy_url:
            cmd.extend(["--proxy", proxy_url])

        startupinfo = None
        try:
            if subprocess._mswindows:  # type: ignore[attr-defined]
                si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
                startupinfo = si
        except Exception:
            pass

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
                startupinfo=startupinfo,
                encoding="utf-8",
            )
        except subprocess.TimeoutExpired:
            self.error.emit(url, "Timeout while fetching metadata (120 seconds)")
            return
        except Exception as e:
            self.error.emit(url, f"Unexpected error: {e}")
            return

        if proc.returncode != 0:
            msg = (proc.stderr or "yt-dlp returned an error").strip()
            self.error.emit(url, msg)
            return

        output = (proc.stdout or "").strip()
        if not output:
            self.error.emit(url, "No metadata received from yt-dlp")
            return

        infos: List[dict[str, Any]] = []
        for line in (l for l in output.splitlines() if l.strip()):
            try:
                infos.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        if not infos:
            self.error.emit(url, "Failed to parse metadata: no valid JSON objects")
            return

        is_playlist = any(
            ("entries" in info) or ("playlist_index" in info) or ("playlist_title" in info)
            for info in infos
        )

        playlist_title = None
        for info in infos:
            pt = info.get("playlist_title")
            if pt:
                playlist_title = pt
                break

        representative = infos[0]
        video_id = representative.get("id") or ""
        thumb_url = representative.get("thumbnail") or ""
        title = playlist_title if (is_playlist and playlist_title) else (representative.get("title") or "Unknown Title")

        # Emit in the same order your MainWindow expects
        self.metadata_fetched.emit(url, title, video_id, thumb_url, is_playlist)
        self.title_fetched.emit(url, title)
