# File: ytget_gui/__main__.py
"""Enables `python -m ytget_gui`."""

from __future__ import annotations

import sys

from ytget_gui.app import main

if __name__ == "__main__":
    sys.exit(main())
