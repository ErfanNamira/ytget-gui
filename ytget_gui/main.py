# File: main.py
"""Launcher shim.

Kept so `python main.py` still works and so PyInstaller has a stable entry
script. The implementation lives in ytget_gui/app.py.
"""

from __future__ import annotations

import sys

from ytget_gui.app import main

if __name__ == "__main__":
    sys.exit(main())
