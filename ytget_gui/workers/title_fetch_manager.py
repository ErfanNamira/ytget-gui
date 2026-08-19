# File: ytget_gui/workers/title_fetch_manager.py

from __future__ import annotations

import subprocess
import threading
from collections import deque
from typing import Deque, List, Optional, Set

from PySide6.QtCore import QObject, Signal, Slot

from ytget_gui.settings import AppSettings
from ytget_gui.workers import fetch_core


class TitleFetchQueue(QObject):
    """
    Serial queue that fetches titles one-by-one in its own thread.
    Signals are forwarded to UI.
    """

    # Forwarded signals
    metadata_fetched = Signal(str, str, str, str, bool)  # url, title, video_id, thumb_url, is_playlist
    title_fetched = Signal(str, str)                     # url, title (legacy)
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
        self._current_url: Optional[str] = None
        self._cancelled_urls: Set[str] = set()

        # Guards _current_proc, which is written from this object's own
        # thread (when a fetch launches) and read/killed from whichever
        # thread calls stop() (normally the GUI thread). Without this,
        # stop() could previously only set a flag that was checked *between*
        # queued items - an in-flight yt-dlp call (up to
        # fetch_core.DEFAULT_TIMEOUT_SECS = 120s) could not be interrupted,
        # which is why stopping the queue or closing the app while a title
        # was mid-fetch would hang until that call finished/timed out.
        self._proc_lock = threading.Lock()
        self._current_proc: Optional[subprocess.Popen] = None

        # Companion to _current_proc, but for the cookie-refresh step that
        # can run *before* any yt-dlp subprocess exists. browser_cookie3
        # talks to OS cookie stores/keychains in-process, so there's no
        # Popen to kill there - instead we hand fetch_core a
        # threading.Event it polls while waiting on that step, and set()
        # it here (guarded by the same lock) so stop()/cancel() can unstick
        # a fetch that's stuck refreshing cookies, not just one stuck in
        # the yt-dlp subprocess. Cleared at the start of each new fetch.
        self._cancel_event = threading.Event()

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
    def stop(self):        # Drop everything still queued, and kill whatever fetch is currently
        # in flight (if any) so we don't sit blocked inside subprocess
        # I/O for up to fetch_core.DEFAULT_TIMEOUT_SECS before honoring
        # the stop. Safe to call from any thread.
        self._stopping = True
        with self._proc_lock:
            proc = self._current_proc
            self._cancel_event.set()
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    @Slot(str)
    def cancel(self, url: str):
        """
        Remove a single URL from the queue without touching the rest.

        If it hasn't started yet, it's just dropped from the deque. If it's
        the one currently in flight, its subprocess is killed so the fetch
        aborts immediately instead of running to completion/timeout and
        (previously) silently re-adding itself once done - which is what
        happened when a card was removed from the UI while its title fetch
        was still running: nothing told the backend queue about it, so the
        fetch kept going and re-inserted the card on success. Safe to call
        from any thread.
        """
        if not url:
            return
        try:
            while url in self._queue:
                self._queue.remove(url)
        except Exception:
            pass
        self._pending.discard(url)

        if self._current_url == url:
            self._cancelled_urls.add(url)
            with self._proc_lock:
                proc = self._current_proc
                self._cancel_event.set()
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _process_next(self):
        # Iterative drain loop (not recursive): a recursive version here
        # grows the call stack by one frame per queued URL and can raise
        # RecursionError on large batches/playlists.
        if self._running:
            return
        self._running = True
        try:
            # BUGFIX: previously `_stopping` was never reset once stop() was
            # called, so every subsequent enqueue() would immediately wipe
            # the queue forever and the worker was permanently dead for the
            # rest of the object's life. Reset it at the start of each drain
            # so a fresh enqueue after stop() actually restarts the queue.
            self._stopping = False

            while True:
                if self._stopping:
                    self._queue.clear()
                    self._pending.clear()
                    break

                if not self._queue:
                    break

                url = self._queue.popleft()
                self.started_one.emit(url)
                try:
                    self._fetch_one(url)
                finally:
                    self._pending.discard(url)
                    self.finished_one.emit(url)
        finally:
            self._running = False
            self.idle.emit()

    def _register_current_proc(self, proc: subprocess.Popen) -> None:
        """Called by fetch_core the instant the yt-dlp subprocess launches,
        so stop() (running on another thread) has something to kill."""
        with self._proc_lock:
            self._current_proc = proc
        if self._stopping:
            # stop() may have run in the tiny window before this callback
            # fired and found nothing to kill yet - handle that race here.
            try:
                proc.kill()
            except Exception:
                pass

    def _fetch_one(self, url: str):
        """
        Inline version of TitleFetcher.run(), but without extra per-job QThread.
        Runs in this worker thread. Emits the same signals expected by MainWindow.
        """
        self._current_url = url
        with self._proc_lock:
            # Fresh per fetch - otherwise a stop()/cancel() from a *previous*
            # url could leave this set and make the very next fetch's cookie
            # refresh return "Cancelled" before it even starts.
            self._cancel_event = threading.Event()
        try:
            if fetch_core.is_spotify_url(url):
                if url in self._cancelled_urls:
                    self._cancelled_urls.discard(url)
                    return
                title = fetch_core.spotify_placeholder_title(url)
                self.metadata_fetched.emit(url, title, "", "", False)
                self.title_fetched.emit(url, title)
                return

            try:
                metadata, err, updated_cookies_path, refresh_warning = fetch_core.fetch_metadata(
                    url=url,
                    yt_dlp_path=self.settings.YT_DLP_PATH,
                    ffmpeg_dir=self.settings.FFMPEG_PATH.parent,
                    cookies_path=self.settings.COOKIES_PATH,
                    proxy_url=self.settings.PROXY_URL or "",
                    settings=self.settings,
                    cookies_from_browser=getattr(self.settings, "COOKIES_FROM_BROWSER", "") or "",
                    on_process_started=self._register_current_proc,
                    cancel_event=self._cancel_event,
                )
            finally:
                with self._proc_lock:
                    self._current_proc = None

            # If cancel(url) fired while this fetch was running, its
            # subprocess was killed above and the result (if any) is stale
            # from the user's point of view - drop it instead of emitting
            # metadata_fetched/error for something that was already removed
            # from the UI.
            if url in self._cancelled_urls:
                self._cancelled_urls.discard(url)
                return

            if updated_cookies_path is not None:
                self.settings.COOKIES_PATH = updated_cookies_path
            if refresh_warning:
                self.error.emit(url, refresh_warning)

            if err is not None:
                self.error.emit(url, err)
                return

            self.metadata_fetched.emit(
                url, metadata.title, metadata.video_id, metadata.thumb_url, metadata.is_playlist
            )
            self.title_fetched.emit(url, metadata.title)
        finally:
            self._current_url = None
