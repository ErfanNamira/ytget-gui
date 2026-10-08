# File: ytget_gui/crashlog.py
"""Persistent logging and crash capture.

A packaged (windowed) build has no console: sys.stderr is None, so a Python
traceback, a Qt fatal message ("QThread: Destroyed while thread is still
running") or a native access violation all vanished and the window simply
closed. Even from a terminal, Qt's fatal messages and native faults print
nothing Python-shaped, which is why "python -m ytget_gui" showed no error.

install() wires every one of those channels into files under
<data dir>/logs/:

    ytget.log   rotating application log (INFO, or DEBUG with --verbose)
    crash.log   native fault tracebacks for every thread (faulthandler),
                plus uncaught Python exceptions and Qt fatal messages

Everything here is best-effort: logging must never be the reason the app
cannot start.
"""

from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import sys
import threading
import time
from pathlib import Path
from typing import IO, Optional

from ytget_gui import _version

log = logging.getLogger("ytget")

_LOG_BYTES = 1_000_000
_LOG_BACKUPS = 3
_CRASH_LOG_MAX_BYTES = 512_000

_crash_file: Optional[IO[str]] = None
_log_dir: Optional[Path] = None


def log_dir() -> Optional[Path]:
    return _log_dir


def _open_crash_file(directory: Path) -> Optional[IO[str]]:
    path = directory / "crash.log"
    try:
        # Keep it bounded: start over once it grows past the cap.
        if path.is_file() and path.stat().st_size > _CRASH_LOG_MAX_BYTES:
            path.replace(directory / "crash.old.log")
        handle = open(path, "a", encoding="utf-8", buffering=1)
        handle.write(
            f"\n=== {_version.APP_NAME} {_version.__version__} session "
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} (Python {sys.version.split()[0]}, "
            f"{sys.platform}) ===\n"
        )
        return handle
    except OSError:
        return None


def _write_crash(text: str) -> None:
    handle = _crash_file
    if handle is None:
        return
    try:
        handle.write(text.rstrip() + "\n")
        handle.flush()
    except (OSError, ValueError):
        pass


def _excepthook(exc_type, exc, tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    import traceback

    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log.critical("Uncaught exception:\n%s", text)
    _write_crash(f"[uncaught exception]\n{text}")


def _thread_excepthook(args) -> None:
    if args.exc_type is SystemExit:
        return
    import traceback

    name = getattr(args.thread, "name", "?")
    text = "".join(
        traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
    )
    log.error("Uncaught exception in thread %s:\n%s", name, text)
    _write_crash(f"[uncaught exception in thread {name}]\n{text}")


def install(data_dir: Path, *, verbose: bool = False) -> Optional[Path]:
    """Configure logging and crash capture. Returns the log directory."""
    global _crash_file, _log_dir

    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"
    )

    # Console only when there is one: a windowed build has sys.stderr None.
    if sys.stderr is not None and not any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    ):
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        root.addHandler(console)

    directory = Path(data_dir) / "logs"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            directory / "ytget.log",
            maxBytes=_LOG_BYTES,
            backupCount=_LOG_BACKUPS,
            encoding="utf-8",
            delay=True,
        )
        handler.setFormatter(fmt)
        root.addHandler(handler)
        _log_dir = directory
    except OSError:
        directory = None  # type: ignore[assignment]

    if directory is not None:
        _crash_file = _open_crash_file(directory)
    try:
        # Native faults (access violation, abort from a Qt fatal) dump the
        # Python stack of every thread here.
        target = _crash_file or sys.stderr
        if target is not None:
            faulthandler.enable(file=target, all_threads=True)
    except (OSError, ValueError, RuntimeError):
        pass

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    return directory


def install_qt_message_handler() -> None:
    """Route Qt's own warnings and fatal messages into the log files."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:  # pragma: no cover
        return

    qt_log = logging.getLogger("qt")
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(msg_type, context, message) -> None:
        level = levels.get(msg_type, logging.WARNING)
        try:
            qt_log.log(level, "%s", message)
            if level >= logging.ERROR:
                where = ""
                if context is not None and getattr(context, "file", None):
                    where = f" ({context.file}:{context.line})"
                _write_crash(f"[qt {logging.getLevelName(level).lower()}] {message}{where}")
        except Exception:  # noqa: BLE001 - a log handler must never raise
            pass

    qInstallMessageHandler(handler)
