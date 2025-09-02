# File: main.py
from __future__ import annotations

import sys
from pathlib import Path
from platform import system

from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtGui import QIcon, QPalette, QColor

from ytget_gui.main_window import MainWindow

__version__ = "2.4.9"


def make_dark_palette() -> QPalette:
    """
    Build a Fusion‐style dark palette covering all common roles.
    """
    pal = QPalette()

    # Core colors
    dark_bg    = QColor("#161A22")
    dark_alt   = QColor("#1E242E")
    light_txt  = QColor("#EAEAF2")
    highlight  = QColor("#3A77FF")

    # Window / widget backgrounds
    pal.setColor(QPalette.Window,         dark_bg)
    pal.setColor(QPalette.Base,           dark_bg)
    pal.setColor(QPalette.AlternateBase,  dark_alt)
    pal.setColor(QPalette.ToolTipBase,    dark_bg)
    pal.setColor(QPalette.ToolTipText,    light_txt)

    # Text
    pal.setColor(QPalette.WindowText,     light_txt)
    pal.setColor(QPalette.Text,           light_txt)
    pal.setColor(QPalette.Button,         dark_bg)
    pal.setColor(QPalette.ButtonText,     light_txt)

    # Selection
    pal.setColor(QPalette.Highlight,      highlight)
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))

    return pal


def main():
    # Handle --version flag
    if "--version" in sys.argv:
        print(f"YTGet version {__version__}")
        sys.exit(0)

    # 1) Create the QApplication before any QWidget
    app = QApplication(sys.argv)

    # 2) Force Qt Fusion style and install our dark palette globally
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(make_dark_palette())

    # 3) Application metadata
    app.setApplicationName("YTGet")
    app.setOrganizationName("YTGet")
    app.setOrganizationDomain("ytget_gui.local")

    # 4) Load the appropriate icon for each platform
    icon_dir = Path(__file__).parent
    if system() == "Darwin":
        # On macOS, prefer .icns
        icns = icon_dir / "icon.icns"
        if icns.exists():
            app.setWindowIcon(QIcon(str(icns)))
        else:
            ico = icon_dir / "icon.ico"
            if ico.exists():
                app.setWindowIcon(QIcon(str(ico)))
    else:
        # On Windows/Linux, use .ico
        ico = icon_dir / "icon.ico"
        if ico.exists():
            app.setWindowIcon(QIcon(str(ico)))

    # 5) Instantiate and show the main window
    w = MainWindow()
    w.show()

    # 6) Enter Qt event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
