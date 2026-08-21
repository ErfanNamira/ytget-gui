# File: ytget_gui/queue/controller.py
"""Queue scheduling and worker lifecycle."""

from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal

from ytget_gui import formats
from ytget_gui.queue.model import QueueItem, QueueModel, Status
from ytget_gui.settings import AppSettings
from ytget_gui.styles import AppStyles
from ytget_gui.utils.text import short
from ytget_gui.utils.validators import is_spotify_url
from ytget_gui.workers.base import CANCELLED_EXIT, BaseDownloadWorker
from ytget_gui.workers.download_worker import DownloadWorker
from ytget_gui.workers.spotdl_worker import SpotDLWorker

log = logging.getLogger(__name__)


class QueueController(QObject):
    """Drives the queue: picks the next item, owns the worker thread, applies
    retry policy, and reports state changes.

    The view observes signals and never touches worker threads itself.
    """

    item_changed = Signal(str)          # url
    queue_changed = Signal()            # structural change (add/remove/reorder)
    overall_progress = Signal(int)
    running_changed = Signal(bool)
    log_message = Signal(str, str)      # text, colour
    queue_finished = Signal()

    def __init__(
        self,
        model: QueueModel,
        settings: AppSettings,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self.settings = settings

        self._thread: Optional[QThread] = None
        self._worker: Optional[BaseDownloadWorker] = None
        self._current: Optional[QueueItem] = None

        self._running = False
        self._paused = True
        self._stop_requested = False
        self._skip_requested = False
        self._finish_announced = False

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def current_item(self) -> Optional[QueueItem]:
        return self._current

    @property
    def can_start(self) -> bool:
        return bool(self.model) and (self._paused or not self._running)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running and not self._paused:
            self._log("\u2139\ufe0f Queue is already running.", AppStyles.INFO_COLOR)
            return
        if not self.model:
            self._log("\u26a0\ufe0f Queue is empty. Add items to start.", AppStyles.WARNING_COLOR)
            return

        # An explicit Start re-arms whatever the user previously skipped or
        # stopped; without this those items are permanently unschedulable and
        # pressing Start on a fully-cancelled queue appears to do nothing.
        rearmed = self.model.rearm_cancelled()
        if rearmed:
            self._log(
                f"\u21bb Re-queued {rearmed} previously stopped item(s).",
                AppStyles.INFO_COLOR,
            )
            self.queue_changed.emit()

        self._paused = False
        self._stop_requested = False
        self._finish_announced = False
        self._log(
            "\u25b6\ufe0f " + ("Resuming" if self._running else "Starting") + " queue\u2026",
            AppStyles.SUCCESS_COLOR,
        )
        self._pump()

    def pause(self) -> None:
        if not self._running:
            self._log("\u2139\ufe0f Queue is not running.", AppStyles.INFO_COLOR)
            return
        self._paused = True
        self._log(
            "\u23f8\ufe0f Queue paused. The current item continues; the next one waits.",
            AppStyles.INFO_COLOR,
        )
        self.running_changed.emit(self._running)

    def skip_current(self) -> None:
        if not (self._running and self._worker is not None):
            return
        self._skip_requested = True
        self._log("\u23ed\ufe0f Skipping current item\u2026", AppStyles.INFO_COLOR)
        self._worker.cancel()

    def stop_all(self) -> None:
        if not self._running:
            self._paused = True
            self.running_changed.emit(False)
            return
        self._stop_requested = True
        self._paused = True
        self._log("\u23f9\ufe0f Stopping current download\u2026", AppStyles.WARNING_COLOR)
        if self._worker is not None:
            self._worker.cancel()

    def cancel_item(self, url: str) -> None:
        """Cancel a specific item if it happens to be the running one."""
        if self._current is not None and self._current.url == url and self._worker:
            self._skip_requested = True
            self._worker.cancel()

    def shutdown(self, timeout_ms: int = 1500) -> None:
        """Stop work and tear the thread down within a bounded budget."""
        self._paused = True
        self._stop_requested = True
        if self._worker is not None:
            try:
                self._worker.cancel()
            except RuntimeError:
                pass
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(timeout_ms)

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _pump(self) -> None:
        if self._paused or self._running:
            self._emit_progress()
            return

        item = self.model.next_runnable()
        if item is None:
            self._announce_finished()
            return

        self._launch(item)

    def _launch(self, item: QueueItem) -> None:
        self._current = item
        self._skip_requested = False
        item.status = Status.DOWNLOADING
        item.progress = 0
        item.stage = ""
        item.last_error = ""

        self._running = True
        self.item_changed.emit(item.url)
        self.running_changed.emit(True)
        self.model.save()

        worker = self._build_worker(item)
        thread = QThread()
        thread.setObjectName("download-thread")
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.log.connect(self.log_message, Qt.QueuedConnection)
        worker.error.connect(self._on_worker_error, Qt.QueuedConnection)
        worker.progress.connect(self._on_worker_progress, Qt.QueuedConnection)
        worker.stage.connect(self._on_worker_stage, Qt.QueuedConnection)
        worker.finished.connect(self._on_worker_finished, Qt.QueuedConnection)
        worker.finished.connect(thread.quit, Qt.QueuedConnection)

        # deleteLater on the thread's own finished signal: deleting the worker
        # from any other context can destroy a QObject that still has queued
        # events pending for it.
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _build_worker(self, item: QueueItem) -> BaseDownloadWorker:
        payload = {
            "url": item.url,
            "title": item.display_title,
            "format_code": item.format_code,
            "video_id": item.video_id,
            "is_playlist": item.is_playlist,
        }
        use_spotdl = is_spotify_url(item.url) or formats.is_spotify_code(item.format_code)
        if use_spotdl:
            return SpotDLWorker(payload, self.settings, self.settings.SPOTDL)
        return DownloadWorker(payload, self.settings)

    # ------------------------------------------------------------------
    # Worker callbacks
    # ------------------------------------------------------------------

    def _on_worker_progress(self, percent: int) -> None:
        item = self._current
        if item is None or item.progress == percent:
            return
        item.progress = percent
        self.item_changed.emit(item.url)
        self._emit_progress()

    def _on_worker_stage(self, text: str) -> None:
        item = self._current
        if item is None:
            return
        # `stage` carries throttled progress text ("45% · 2.1MiB/s · ETA 00:12").
        # The previous revision wrote this into the item's *status* field, which
        # corrupted the status chip and left the progress bar pinned at 0%.
        item.stage = text
        self.item_changed.emit(item.url)

    def _on_worker_error(self, message: str) -> None:
        item = self._current
        if item is not None:
            item.last_error = message
        self._log(f"\u274c {message}", AppStyles.ERROR_COLOR)

    def _on_worker_finished(self, code: int) -> None:
        item = self._current
        self._current = None
        self._running = False

        if item is not None:
            self._apply_outcome(item, code)
            self.item_changed.emit(item.url)
            self.model.save()

        self._worker = None
        self.running_changed.emit(False)
        self._emit_progress()

        if self._stop_requested:
            self._stop_requested = False
            self._log(
                "\u23f9\ufe0f Stopped. The queue is paused; remaining items are untouched.",
                AppStyles.WARNING_COLOR,
            )
            return

        if self._paused:
            return

        # Defer so the finishing thread can unwind before the next launch;
        # starting a new QThread from inside the old one's finished handler is
        # how the previous revision ended up with two live workers.
        QTimer.singleShot(0, self._pump)

    def _on_thread_finished(self) -> None:
        self._thread = None

    def _apply_outcome(self, item: QueueItem, code: int) -> None:
        cancelled = code == CANCELLED_EXIT or self._skip_requested or self._stop_requested

        if code == 0:
            item.status = Status.COMPLETED
            item.progress = 100
            item.stage = ""
            item.queue_attempts = 0
            return

        if cancelled:
            # A user-initiated stop leaves the item in place, untouched by the
            # retry counter, and non-schedulable until Start is pressed again.
            item.status = Status.CANCELLED
            item.progress = 0
            item.stage = ""
            return

        # Genuine failure. DownloadWorker has already exhausted its in-process
        # retries for transient errors by this point.
        item.queue_attempts += 1
        item.progress = 0
        item.stage = ""
        max_requeues = max(0, int(getattr(self.settings, "QUEUE_ERROR_RETRIES", 2)))
        label = short(item.display_title, 60)

        if item.queue_attempts <= max_requeues:
            # Move to the back rather than dropping it: the failure is often
            # site-wide rate limiting rather than item-specific, so it deserves
            # another attempt once the rest of the queue has run.
            item.status = Status.PENDING
            self.model.move_to_end(item)
            self._log(
                f"\u21a9\ufe0f '{label}' failed \u2014 moved to the end of the queue to retry "
                f"later (attempt {item.queue_attempts}/{max_requeues}).",
                AppStyles.WARNING_COLOR,
            )
            self.queue_changed.emit()
        else:
            item.status = Status.ERROR
            self.model.move_to_end(item)
            self._log(
                f"\u274c '{label}' failed again \u2014 kept in the queue and marked as Error.",
                AppStyles.ERROR_COLOR,
            )
            self.queue_changed.emit()

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    def _announce_finished(self) -> None:
        # Guarded because completion is reachable from two paths at once (the
        # scheduler finding nothing runnable, and the last worker finishing).
        # Unguarded, a post-queue "Shutdown" ran `shutdown /s` twice.
        if self._finish_announced:
            return
        self._finish_announced = True
        self._paused = True
        self._running = False
        self.running_changed.emit(False)
        self._emit_progress()
        self.queue_finished.emit()

    # ------------------------------------------------------------------
    # Queue edits
    # ------------------------------------------------------------------

    def add_item(self, item: QueueItem) -> bool:
        if not self.model.add(item):
            return False
        self._finish_announced = False
        self.queue_changed.emit()
        self.model.save()
        self._emit_progress()
        return True

    def remove_items(self, urls: List[str]) -> int:
        removed = 0
        for url in urls:
            if self._current is not None and self._current.url == url:
                self.cancel_item(url)
            if self.model.remove(url) is not None:
                removed += 1
        if removed:
            self.queue_changed.emit()
            self.model.save()
            self._emit_progress()
        return removed

    def clear_completed(self) -> int:
        removed = self.model.remove_completed()
        if removed:
            self.queue_changed.emit()
            self.model.save()
            self._emit_progress()
        return len(removed)

    def move_selection(self, urls: List[str], *, to_top: bool) -> None:
        # Keep the running item pinned at the head so "send to top" cannot
        # reorder the queue out from under an active download.
        reserved = 1 if (self._current is not None and to_top) else 0
        filtered = [u for u in urls if self._current is None or u != self._current.url]
        if not filtered:
            return
        self.model.move_many(filtered, to_top=to_top, after=reserved)
        self.queue_changed.emit()
        self.model.save()

    def apply_visual_order(self, urls: List[str]) -> None:
        self.model.reorder_by_urls(urls)
        if self._current is not None:
            self.model.move_many(
                [self._current.url], to_top=True, after=0
            )
        self.model.save()

    def sort_by(self, key: str) -> None:
        self.model.sort_by(key)
        if self._current is not None:
            self.model.move_many([self._current.url], to_top=True, after=0)
        self.queue_changed.emit()
        self.model.save()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit_progress(self) -> None:
        self.overall_progress.emit(self.model.overall_progress(self._current))

    def _log(self, text: str, colour: str) -> None:
        self.log_message.emit(text, colour)
