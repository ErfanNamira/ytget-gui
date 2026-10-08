"""Worker/thread lifetime and crash-resilience regressions (2.8.3).

The "app silently closes mid-download" reports traced back to the queue
controller releasing its only references to a running worker and to a QThread
that had emitted finished() but not yet ended, plus deferred deletes racing
both. These tests drive the real controller with workers that keep running
after they report completion -- the exact window the old code got wrong.
"""

from __future__ import annotations

import gc
import tempfile
import threading
import time
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer

from ytget_gui.queue.controller import QueueController
from ytget_gui.queue.model import QueueItem, QueueModel, Status
from ytget_gui.workers.base import BaseDownloadWorker


def _app():
    return QCoreApplication.instance() or QCoreApplication([])


class _LingeringWorker(BaseDownloadWorker):
    """Reports success, then keeps executing inside its own thread."""

    destroyed_on = []
    main_thread = None

    def _start(self) -> None:
        self.emit_progress(50)
        self.emit_finished(0)
        # Still inside the worker after finished: the old controller could
        # destroy this object right now from the GUI thread.
        time.sleep(0.05)
        self.objectName()  # raises RuntimeError if the C++ side is gone
        self._still_alive = True

    def _do_cancel(self) -> None:
        pass


class _ExplodingWorker(BaseDownloadWorker):
    """Raises inside a queued slot; the queue must still move on."""

    def _start(self) -> None:
        QTimer.singleShot(0, lambda: self._guarded(self._boom))

    def _boom(self) -> None:
        raise ValueError("synthetic failure")

    def _do_cancel(self) -> None:
        pass


class ControllerLifecycleTests(unittest.TestCase):
    def _run(self, worker_cls, count):
        app = _app()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        from ytget_gui.settings import AppSettings

        root = Path(tmp.name)
        settings = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
        model = QueueModel(root / "queue.json")
        controller = QueueController(model, settings)
        built = []

        def build(item):
            w = worker_cls({"url": item.url, "title": item.title})
            built.append(w)
            return w

        controller._build_worker = build
        for i in range(count):
            controller.add_item(QueueItem(url=f"https://example.com/{i}", title=str(i)))
        controller.queue_finished.connect(lambda: QTimer.singleShot(50, app.quit))
        QTimer.singleShot(0, controller.start)
        QTimer.singleShot(20_000, app.quit)
        app.exec()
        return controller, model, built

    def test_many_items_finish_and_dispose_cleanly(self):
        controller, model, built = self._run(_LingeringWorker, 12)
        self.assertEqual(len(built), 12)
        self.assertTrue(all(i.status is Status.COMPLETED for i in model))
        # Every worker survived past its own finished() ...
        self.assertTrue(all(getattr(w, "_still_alive", False) for w in built))
        # ... and was then destroyed deterministically by the controller.
        import shiboken6
        self.assertFalse(any(shiboken6.isValid(w) for w in built))
        self.assertIsNone(controller.thread)
        gc.collect()

    def test_exception_in_worker_slot_fails_item_without_stalling(self):
        controller, model, built = self._run(_ExplodingWorker, 2)
        self.assertEqual(len(built), 2 + 2 * 2)  # first runs + queue re-tries
        self.assertTrue(all(i.status is Status.ERROR for i in model))
        self.assertIn("synthetic failure", next(iter(model)).last_error)


_STRESS = r"""
import sys
sys.path.insert(0, {root!r})
import tests.test_v283_lifecycle as t

class Instant(t._LingeringWorker):
    def _start(self):
        self.emit_finished(0)

case = t.ControllerLifecycleTests("test_many_items_finish_and_dispose_cleanly")
_c, model, _b = case._run(Instant, 300)
done = sum(i.status is t.Status.COMPLETED for i in model)
print("DONE", done)
sys.exit(0 if done == 300 else 3)
"""


class ControllerStressTests(unittest.TestCase):
    def test_rapid_back_to_back_items_do_not_crash(self):
        """2.8.2 segfaulted here (exit 139) every run: dropping the QThread
        from the finished() slot destroyed it while still running."""
        import os
        import subprocess
        import sys

        root = str(Path(__file__).resolve().parents[1])
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        result = subprocess.run(
            [sys.executable, "-c", _STRESS.format(root=root)],
            capture_output=True, text=True, timeout=120, env=env, cwd=root,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DONE 300", result.stdout)


class CrashLogTests(unittest.TestCase):
    def test_install_creates_logs_and_captures_thread_exceptions(self):
        from ytget_gui import crashlog

        with tempfile.TemporaryDirectory() as tmp:
            directory = crashlog.install(Path(tmp))
            self.assertTrue((directory / "crash.log").is_file())

            def boom():
                raise RuntimeError("thread boom")

            t = threading.Thread(target=boom, name="boom-thread")
            t.start()
            t.join()
            text = (directory / "crash.log").read_text(encoding="utf-8")
            self.assertIn("thread boom", text)
            self.assertIn("boom-thread", text)
            # Release file handles so the temp dir can be removed on Windows.
            import faulthandler, logging
            faulthandler.disable()
            for h in list(logging.getLogger().handlers):
                if isinstance(h, logging.FileHandler):
                    h.close()
                    logging.getLogger().removeHandler(h)
            if crashlog._crash_file:
                crashlog._crash_file.close()
                crashlog._crash_file = None
            import sys
            sys.excepthook = sys.__excepthook__
            threading.excepthook = threading.__excepthook__


if __name__ == "__main__":
    unittest.main()
