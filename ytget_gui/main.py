# File: main.py
"""YTGet entry point.

Kept deliberately thin: argument handling, Qt bootstrapping, palette/style
installation, then hand off to MainWindow.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# AppUserModelID must be set before QApplication is constructed, or Windows
# groups the window under the generic python.exe taskbar entry.
if sys.platform == "win32":
    import ctypes

    try:
        from ytget_gui._version import __version__ as _v

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"YTGet.{_v}")
    except Exception:  # noqa: BLE001 - cosmetic only, never fatal
        pass

from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from ytget_gui import _version
from ytget_gui.styles import Palette, global_font, refresh_styles

log = logging.getLogger("ytget")


def build_dark_palette() -> QPalette:
    """Fusion dark palette covering the roles QSS does not reach.

    Native popups, tooltips and disabled states fall back to the palette
    rather than the stylesheet, so all of them are set explicitly.
    """
    pal = QPalette()

    bg = QColor(Palette.WINDOW_BG)
    alt = QColor(Palette.WIDGET_BG)
    text = QColor(Palette.TEXT)
    accent = QColor(Palette.ACCENT)
    disabled = QColor(120, 120, 132)

    for role in (QPalette.Window, QPalette.Base, QPalette.Button,
                 QPalette.ToolTipBase):
        pal.setColor(role, bg)
    pal.setColor(QPalette.AlternateBase, alt)

    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText,
                 QPalette.ToolTipText, QPalette.BrightText):
        pal.setColor(role, text)

    pal.setColor(QPalette.Highlight, accent)
    pal.setColor(QPalette.HighlightedText, bg)
    pal.setColor(QPalette.Link, accent)
    pal.setColor(QPalette.LinkVisited, QColor(Palette.ACCENT_ALT))

    pal.setColor(QPalette.Mid, alt)
    pal.setColor(QPalette.Midlight, QColor(40, 40, 62))
    pal.setColor(QPalette.Dark, QColor(6, 8, 16))
    pal.setColor(QPalette.Shadow, QColor(0, 0, 0))

    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText,
                 QPalette.HighlightedText):
        pal.setColor(QPalette.Disabled, role, disabled)

    return pal


def find_icon() -> QIcon | None:
    """Locate the app icon in both source and frozen layouts."""
    from ytget_gui.utils.paths import get_base_path, get_bundle_path, is_macos

    names = ("icon.icns", "icon.ico", "icon.png") if is_macos() else ("icon.ico", "icon.png")
    roots = (get_bundle_path(), get_base_path(), get_bundle_path() / "_internal")

    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return QIcon(str(candidate))
    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ytget", add_help=True)
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    parser.add_argument("urls", nargs="*", help="URLs to enqueue on startup")
    # Qt swallows its own flags; ignore anything we do not recognise so
    # -platform/-style still work.
    args, _unknown = parser.parse_known_args(argv)
    return args


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    if args.version:
        print(f"{_version.APP_NAME} {_version.__version__}")
        return 0

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setApplicationName(_version.APP_NAME)
    app.setApplicationVersion(_version.__version__)
    app.setOrganizationName(_version.ORG_NAME)
    app.setOrganizationDomain(_version.ORG_DOMAIN)

    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(build_dark_palette())

    # QApplication and its primary screen now exist, so DPI-scaled QSS can
    # finally be computed for real.
    refresh_styles()
    app.setFont(global_font())

    icon = find_icon()
    if icon is not None:
        app.setWindowIcon(icon)

    # Imported after Qt is up: MainWindow constructs widgets at import-adjacent
    # time and pulls in the whole worker stack.
    from ytget_gui.main_window import MainWindow

    window = MainWindow(app_icon=icon)
    window.show()

    if args.urls:
        window.enqueue_urls(args.urls)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
