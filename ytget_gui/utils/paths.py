# File: ytget_gui/utils/paths.py
from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path

def get_base_path() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def is_windows() -> bool:
    return sys.platform.startswith("win")

def executable_name(base: str) -> str:
    return f"{base}.exe" if is_windows() else base

def which_or_path(candidate: Path, fallback_name: str) -> Path:
    # Prefer candidate path if exists, otherwise search PATH
    if candidate.exists():
        return candidate
    found = shutil.which(fallback_name)
    if found:
        return Path(found)
    return candidate  # return original for error messaging

def default_downloads_dir() -> Path:
    # Respect OS defaults
    if is_windows():
        return Path(os.path.join(os.getcwd(), "Downloads")).resolve()
    # Try XDG or fallback to cwd/Downloads
    xdg_download = Path.home() / "Downloads"
    return xdg_download if xdg_download.exists() else Path(os.getcwd()) / "Downloads"