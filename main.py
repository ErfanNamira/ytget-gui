from __future__ import annotations

import sys
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from ytget.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("YTGet")
    app.setOrganizationName("YTGet")
    app.setOrganizationDomain("ytget.local")

    icon_path = Path(__file__).parent / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
