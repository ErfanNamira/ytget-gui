from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication
from ytget.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("YTGet")
    app.setOrganizationName("YTGet")
    app.setOrganizationDomain("ytget.local")

    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()