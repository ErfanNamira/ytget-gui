# File: main.py
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ytget_gui.main_window import MainWindow
# from ytget_gui.utils.firewall_manager import check_network_firewall


def main():
    # 1) Create the QApplication before any QWidget (e.g. QMessageBox in firewall check)
    app = QApplication(sys.argv)
    app.setApplicationName("YTGet")
    app.setOrganizationName("YTGet")
    app.setOrganizationDomain("ytget_gui.local")

    # 2) Set the window icon if available
    icon_path = Path(__file__).parent / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # 3) Every launch: verify network/firewall & yt-dlp availability
    # check_network_firewall(parent=None)

    # 4) Instantiate and show the main window
    w = MainWindow()
    w.show()

    # 5) Enter Qt event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()