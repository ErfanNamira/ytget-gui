# File: ytget_gui/app.py
"""Application bootstrap: argument handling, Qt setup, then MainWindow.

Lives inside the package so `python -m ytget_gui`, a console_scripts entry
point, and the root main.py shim can all share one implementation.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time

# AppUserModelID must be set before QApplication is constructed, or Windows
# groups the window under the generic python.exe taskbar entry.
if sys.platform == "win32":
    import ctypes

    try:
        from ytget_gui._version import APP_USER_MODEL_ID

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception:  # noqa: BLE001 - cosmetic only, never fatal
        pass

from ytget_gui import _version

log = logging.getLogger("ytget")


def build_dark_palette() -> QPalette:
    """Fusion dark palette covering the roles QSS does not reach.

    Native popups, tooltips and disabled states fall back to the palette
    rather than the stylesheet, so all of them are set explicitly.
    """
    from PySide6.QtGui import QColor, QPalette
    from ytget_gui.styles import Palette
    pal = QPalette()

    bg = QColor(Palette.WINDOW_BG)
    alt = QColor(Palette.WIDGET_BG)
    text = QColor(Palette.TEXT)
    accent = QColor(Palette.ACCENT)
    disabled = QColor(120, 120, 132)

    for role in (QPalette.Window, QPalette.Base, QPalette.Button, QPalette.ToolTipBase):
        pal.setColor(role, bg)
    pal.setColor(QPalette.AlternateBase, alt)

    for role in (
        QPalette.WindowText, QPalette.Text, QPalette.ButtonText,
        QPalette.ToolTipText, QPalette.BrightText,
    ):
        pal.setColor(role, text)

    pal.setColor(QPalette.Highlight, accent)
    pal.setColor(QPalette.HighlightedText, bg)
    pal.setColor(QPalette.Link, accent)
    pal.setColor(QPalette.LinkVisited, QColor(Palette.ACCENT_ALT))

    pal.setColor(QPalette.Mid, alt)
    pal.setColor(QPalette.Midlight, QColor(40, 40, 62))
    pal.setColor(QPalette.Dark, QColor(6, 8, 16))
    pal.setColor(QPalette.Shadow, QColor(0, 0, 0))

    for role in (
        QPalette.WindowText, QPalette.Text,
        QPalette.ButtonText, QPalette.HighlightedText,
    ):
        pal.setColor(QPalette.Disabled, role, disabled)

    return pal


def find_icon() -> QIcon | None:
    """Locate the app icon in both source and frozen layouts.

    Every size stored in the .ico is loaded, not just the one Qt happens to
    pick: Windows asks for a 16px icon for the taskbar button, and an icon
    that only carries a large bitmap is rejected as "no icon" the first time
    it is requested after a cold boot, before the shell icon cache is warm.
    """
    from PySide6.QtGui import QIcon
    from ytget_gui.utils.paths import get_base_path, get_bundle_path, is_macos

    names = (
        ("icon.icns", "icon.ico", "icon.png") if is_macos() else ("icon.ico", "icon.png")
    )
    roots = (get_bundle_path(), get_base_path(), get_base_path() / "_internal")

    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                icon = QIcon(str(candidate))
                if not icon.isNull():
                    return icon
    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ytget")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument("--doctor", action="store_true", help="check dependencies and storage without opening the GUI")
    parser.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="start hidden in the system tray (used by the startup entry)",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=0,
        metavar="SECONDS",
        help="wait before starting, so the network is ready at login",
    )
    parser.add_argument("urls", nargs="*", help="URLs to enqueue on startup")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    if args.version:
        print(f"{_version.APP_NAME} {_version.__version__}")
        return 0

    if args.doctor:
        from ytget_gui.diagnostics import main as doctor
        return doctor()

    try:
        from PySide6.QtWidgets import QApplication, QStyleFactory, QMessageBox
        from PySide6.QtCore import QLockFile
        from ytget_gui.styles import global_font, refresh_styles
    except ImportError as exc:
        print(f"YTGet cannot open the desktop interface: {exc}\nRun install.py with Python, or python -m pip install .", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    # Sleep before Qt starts: at login the network and the tray host
    # are often not ready yet, and no window exists to look frozen.
    if args.delay > 0:
        import time

        time.sleep(min(600, args.delay))

    app = QApplication(sys.argv)
    app.setApplicationName(_version.APP_NAME)
    app.setApplicationVersion(_version.__version__)
    app.setOrganizationName(_version.ORG_NAME)
    app.setOrganizationDomain(_version.ORG_DOMAIN)

    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(build_dark_palette())

    # QApplication and its primary screen now exist, so the DPI-scaled QSS can
    # finally be computed for real instead of at the 1.0 placeholder scale.
    refresh_styles()
    app.setFont(global_font())

    icon = find_icon()
    if icon is not None:
        app.setWindowIcon(icon)

    # Imported after Qt is up: MainWindow builds widgets and pulls in the
    # whole worker stack.
    from ytget_gui.main_window import MainWindow

    # A second writer would silently overwrite queue.json and config.json.
    from ytget_gui.utils.paths import get_data_path
    data_dir = get_data_path()
    data_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data_dir / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "YTGet is already open", "Use the existing window, or a different YTGET_DATA_DIR profile.")
        return 1
    try:
        window = MainWindow(app_icon=icon)
    except Exception as exc:
        log.exception("Startup failed")
        QMessageBox.critical(None, "YTGet could not start", f"{exc}\nRun python -m ytget_gui --doctor for dependency checks.")
        return 2
    if args.minimized and getattr(window, "tray", None) is not None \
            and window.tray.available:
        window.hide()
    elif args.minimized:
        # No tray host available, so a minimised window is the only
        # way to stay reachable.
        window.showMinimized()
    else:
        window.show()

    if args.urls:
        window.enqueue_urls(args.urls)

    code = app.exec()

    # Normal teardown runs first: killing the process outright while Qt still
    # has live thread-local storage makes it complain on the way out
    # ("QThreadStorage: entry N destroyed before end of thread").
    #
    # The watchdog is the backstop for the case that caused the hard exit in
    # the first place: a background helper parked in a socket read, which
    # concurrent.futures' atexit hook then waits on forever, leaving YTGet in
    # Task Manager with no window. Everything that must be persisted has
    # already been written by MainWindow.closeEvent, so if the interpreter is
    # still here a few seconds later there is nothing left to lose.
    _arm_exit_watchdog(int(code))
    return int(code)


# Seconds allowed for a clean interpreter shutdown before the process is
# terminated outright.
_EXIT_WATCHDOG_S = 5.0


def _arm_exit_watchdog(code: int) -> None:
    def _bail() -> None:
        time.sleep(_EXIT_WATCHDOG_S)
        log.warning("Shutdown stalled after %.0fs; exiting.", _EXIT_WATCHDOG_S)
        try:
            logging.shutdown()
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:  # noqa: BLE001
            pass
        os._exit(code)

    # Daemon: it must never be the reason the process stays up.
    threading.Thread(target=_bail, name="ExitWatchdog", daemon=True).start()
