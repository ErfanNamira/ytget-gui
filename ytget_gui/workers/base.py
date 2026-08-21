# File: ytget_gui/workers/base.py
"""Common base for cancellable, log-emitting download workers.

DownloadWorker and SpotDLWorker previously duplicated timer setup, log
buffering, throttled status emission and cancel bookkeeping, with subtly
different behaviour in each. The queue controller can now treat any subclass
identically.

Signals
-------
log(text, colour)   Console output.
progress(percent)   0-100, monotonic within an attempt.
stage(text)         Short human-readable state, e.g. "45% · 3.2MiB/s · ETA 00:12".
finished(code)      0 success, -1 cancelled, anything else a real failure.
error(text)         Fatal problem description (also logged by the receiver).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from ytget_gui.styles import AppStyles
from ytget_gui.workers.log_buffer import LogBuffer, coalesce

log = logging.getLogger(__name__)

CANCELLED_EXIT = -1


class BaseDownloadWorker(QObject):
    log = Signal(str, str)
    progress = Signal(int)
    stage = Signal(str)
    finished = Signal(int)
    error = Signal(str)
    output = Signal(str, int)   # final path, number of files produced

    def __init__(
        self,
        item: Dict[str, Any],
        *,
        log_flush_ms: int = 250,
        stage_throttle_ms: int = 400,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.item = item
        self._cancelled = False
        self._finished_emitted = False

        self._buffer = LogBuffer()
        self._log_timer: Optional[QTimer] = None
        self._log_flush_ms = max(50, int(log_flush_ms))

        self._stage_throttle_s = max(0.05, stage_throttle_ms / 1000.0)
        self._last_stage_text: Optional[str] = None
        self._last_stage_at = 0.0
        self._last_percent = -1

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def url(self) -> str:
        return str(self.item.get("url", ""))

    @property
    def title(self) -> str:
        return str(self.item.get("title") or self.url or "Unknown")

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    # ------------------------------------------------------------------
    # Lifecycle -- subclasses override _start()
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Entry point connected to QThread.started."""
        try:
            self._start_log_timer()
            self._start()
        except Exception as exc:  # noqa: BLE001 - must not kill the thread
            log.exception("Worker failed to start")
            self.error.emit(f"Error preparing download: {exc}")
            self.flush_now()
            self.emit_finished(CANCELLED_EXIT)

    def _start(self) -> None:
        raise NotImplementedError

    def cancel(self) -> None:
        """Request cancellation. Safe to call from any thread."""
        if self._cancelled:
            return
        self._cancelled = True
        self.add_log("\u23f9\ufe0f Cancelling\u2026", AppStyles.WARNING_COLOR)
        self.flush_now()
        self._do_cancel()

    def _do_cancel(self) -> None:
        raise NotImplementedError

    def emit_finished(self, code: int) -> None:
        """Emit `finished` exactly once.

        A worker can reach completion from several paths at once (process exit
        racing a cancel, or a spawn failure after a partial start). Emitting
        twice made the queue controller advance two items for one job.
        """
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self._stop_log_timer()
        self.flush_now()
        self.finished.emit(code)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _start_log_timer(self) -> None:
        if self._log_timer is not None:
            return
        # Parented to self so the timer lives in the worker's thread affinity;
        # a timer created on the GUI thread would never fire here.
        timer = QTimer(self)
        timer.setInterval(self._log_flush_ms)
        timer.timeout.connect(self.flush)
        timer.start()
        self._log_timer = timer

    def _stop_log_timer(self) -> None:
        timer = self._log_timer
        if timer is not None and timer.isActive():
            timer.stop()

    def add_log(self, text: str, colour: str = AppStyles.TEXT_COLOR) -> None:
        self._buffer.add(text, colour)
        if len(self._buffer) > 800:
            self.flush()

    def flush(self) -> None:
        for text, colour in self._buffer.drain():
            self.log.emit(text, colour)

    def flush_now(self) -> None:
        """Synchronous flush that ignores the per-flush cap.

        Used for start/finish banners, which must reach the console before the
        worker's thread is torn down.
        """
        entries = self._buffer.drain()
        while self._buffer:
            entries.extend(self._buffer.drain())
        for text, colour in coalesce(entries):
            self.log.emit(text, colour)

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def emit_progress(self, percent: int) -> None:
        value = max(0, min(100, int(percent)))
        if value == self._last_percent:
            return
        self._last_percent = value
        self.progress.emit(value)

    def reset_progress(self) -> None:
        self._last_percent = -1

    def emit_stage(self, text: str, *, force: bool = False) -> None:
        if not text:
            return
        now = time.monotonic()
        if not force:
            if text == self._last_stage_text:
                return
            if (now - self._last_stage_at) < self._stage_throttle_s:
                return
        self._last_stage_text = text
        self._last_stage_at = now
        self.stage.emit(text)

    def emit_output(self, path: str, count: int = 1) -> None:
        if path:
            self.output.emit(path, max(1, int(count)))
