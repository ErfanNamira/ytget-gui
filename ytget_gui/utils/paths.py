# File: ytget_gui/utils/paths.py

from __future__ import annotations

import os
import sys
import platform
import shutil
from pathlib import Path
from typing import Union


def get_base_path() -> Path:
    """
    Return the directory where the app is running from.
    If frozen by PyInstaller, use the _MEIPASS bundle directory or
    the executable’s parent folder. Otherwise return the repo root.
    """
    if getattr(sys, "frozen", False):
        # When bundled by PyInstaller
        return Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(sys.executable).parent
    # Running from source
    return Path(__file__).resolve().parent.parent


def is_windows() -> bool:
    """
    Return True if the current OS is Windows.
    """
    return platform.system().lower().startswith("win")


def executable_name(base: str) -> str:
    """
    Append `.exe` on Windows, leave unchanged on macOS/Linux.
    """
    return f"{base}.exe" if is_windows() else base


def which_or_path(candidate: Union[Path, str], exe_name: str) -> Path:
    """
    Resolve an executable according to:
      1) If `candidate` exists as a file, return it.
      2) Otherwise, search the system PATH for `exe_name`.
      3) Fallback to `candidate` (even if it doesn’t exist,
         so you can see a clear error when you try to run it).
    """
    cand = Path(candidate)
    if cand.exists() and cand.is_file():
        return cand

    system_path = shutil.which(exe_name)
    if system_path:
        return Path(system_path)

    return cand


def default_downloads_dir() -> Path:
    """
    Determine a reasonable default downloads folder:
      - On Windows: ./Downloads under cwd
      - On macOS/Linux: ~/Downloads if it exists, otherwise ./Downloads
    """
    if is_windows():
        return Path(os.path.join(os.getcwd(), "Downloads")).resolve()

    xdg = Path.home() / "Downloads"
    if xdg.exists() and xdg.is_dir():
        return xdg

    return (Path(os.getcwd()) / "Downloads").resolve()