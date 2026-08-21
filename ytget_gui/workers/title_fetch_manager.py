# File: ytget_gui/workers/title_fetch_manager.py
"""Serial metadata-fetch queue running in its own thread."""

from __future__ import annotations

import logging
import subprocess
import threading
from collections import deque
from typing import Deque, Iterable, List, Optional, Set

from PySide6.QtCore import QObject, Signal, Slot

from ytget_gui.workers import fetch_core, proc

log = logging.getLogger(__name__)


class TitleFetchQueue(QObject):
    """Fetches metadata one URL at a time, cancellable mid-flight.

    Serial by design: yt-dlp metadata extraction is the operation most likely
    to trip YouTube's bot detection, and firing several in parallel when a user
    drops twenty URLs is what gets an IP rate-limited.
    """

    metadata_fetched = Signal(str, str, str, str, bool)
    title_fetched = Signal(str, str)
    error = Signal(str, str)
    started_one = Signal(str)
    finished_one = Signal(str)
    idle = Signal()

    def __init__(self, settings, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.settings = settings

        self._queue: Deque[str] = deque()
        self._pending: Set[str] = set()
        self._cancelled: Set[str] = set()
        self._draining = False
        self._stopping = False
        self._current_url: Optional[str] = None

        # Guards _current_proc and _cancel_event. _current_proc is written from
        # this object's thread when a fetch launches and read/killed from
        # whichever thread calls stop()/cancel() -- normally the GUI thread.
        # Without a cross-thread kill, stop() could only set a flag checked
        # *between* items, so an in-flight fetch blocked shutdown for up to
        # DEFAULT_TIMEOUT_SECS.
        self._lock = threading.Lock()
        self._current_proc: Optional[subprocess.Popen] = None
        # Companion for the cookie-refresh step, which runs before any
        # subprocess exists and has no PID to signal.
        self._cancel_event = threading.Event()

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    @Slot(str)
    def enqueue(self, url: str) -> None:
        self.enqueue_many([url])

    @Slot(list)
    def enqueue_many(self, urls: Iterable[str]) -> None:
        added = False
        for url in urls:
            if not url or url in self._pending:
                continue
            self._queue.append(url)
            self._pending.add(url)
            self._cancelled.discard(url)
            added = True
        if added and not self._draining:
            self._drain()

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    @Slot()
    def stop(self) -> None:
        """Drop the backlog and abort the in-flight fetch. Any thread."""
        self._stopping = True
        self._queue.clear()
        with self._lock:
            self._cancel_event.set()
            process = self._current_proc
        proc.terminate_tree(process)

    @Slot(str)
    def cancel(self, url: str) -> None:
        """Remove one URL without disturbing the rest.

        If it is the in-flight fetch, its subprocess is killed so the fetch
        aborts now. Previously nothing told this queue that a card had been
        removed from the UI, so the fetch ran to completion and its success
        handler re-inserted the card the user had just deleted.
        """
        if not url:
            return

        try:
            while url in self._queue:
                self._queue.remove(url)
        except ValueError:
            pass
        self._pending.discard(url)

        if self._current_url != url:
            return

        self._cancelled.add(url)
        with self._lock:
            self._cancel_event.set()
            process = self._current_proc
        proc.terminate_tree(process)

    # ------------------------------------------------------------------
    # Draining
    # ------------------------------------------------------------------

    def _drain(self) -> None:
        """Iterative, not recursive: recursing per URL grew the stack one frame
        per item and raised RecursionError on large playlist batches."""
        if self._draining:
            return
        self._draining = True
        # Reset here, not in stop(): leaving _stopping latched meant every
        # later enqueue() wiped the queue immediately and the worker was dead
        # for the remainder of the process lifetime.
        self._stopping = False
        try:
            while self._queue and not self._stopping:
                url = self._queue.popleft()
                self.started_one.emit(url)
                try:
                    self._fetch_one(url)
                except Exception:  # noqa: BLE001 - one bad URL must not stop the queue
                    log.exception("Title fetch crashed for %s", url)
                    self.error.emit(url, "Unexpected error while fetching metadata")
                finally:
                    self._pending.discard(url)
                    self.finished_one.emit(url)

            if self._stopping:
                self._queue.clear()
                self._pending.clear()
        finally:
            self._draining = False
            self.idle.emit()

    def _register_proc(self, process: subprocess.Popen) -> None:
        """Called the instant the subprocess launches, so stop() has a target."""
        with self._lock:
            self._current_proc = process
            already_cancelling = self._stopping or self._cancel_event.is_set()
        if already_cancelling:
            # stop()/cancel() may have run in the window before this fired and
            # found nothing to kill.
            proc.terminate_tree(process)

    def _fetch_one(self, url: str) -> None:
        self._current_url = url
        with self._lock:
            # Fresh per fetch: a stale set event from a previous URL would make
            # the next fetch report Cancelled before it began.
            self._cancel_event = threading.Event()
            cancel_event = self._cancel_event

        try:
            result = fetch_core.fetch_metadata(
                url=url,
                yt_dlp_path=self.settings.YT_DLP_PATH,
                ffmpeg_dir=self.settings.FFMPEG_PATH.parent,
                cookies_path=self.settings.COOKIES_PATH,
                proxy_url=self.settings.PROXY_URL or "",
                settings=self.settings,
                cookies_from_browser=getattr(self.settings, "COOKIES_FROM_BROWSER", "")
                or "",
                on_process_started=self._register_proc,
                cancel_event=cancel_event,
            )
        finally:
            with self._lock:
                self._current_proc = None
            self._current_url = None

        # A result for a cancelled URL is stale from the user's point of view.
        if url in self._cancelled:
            self._cancelled.discard(url)
            return
        if result.cancelled:
            return

        if result.cookies_path is not None:
            self.settings.COOKIES_PATH = result.cookies_path
        if result.warning:
            self.error.emit(url, result.warning)

        if not result.ok:
            self.error.emit(url, result.error or "Unknown error")
            return

        md = result.metadata
        self.metadata_fetched.emit(
            url, md.title, md.video_id, md.thumb_url, md.is_playlist
        )
        self.title_fetched.emit(url, md.title)
