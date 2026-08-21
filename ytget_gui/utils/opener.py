# File: ytget_gui/utils/opener.py
"""Open files and folders in the user's desktop environment.

Every function returns a bool and never raises. A download that finished
months ago may since have been moved, renamed or deleted, and the user
clicking Play on it must produce a message, not a traceback.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

log = logging.getLogger(__name__)

PathLike = Union[str, Path]


def _hidden_kwargs() -> dict:
    if sys.platform != "win32":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startupinfo}


def open_path(target: Optional[PathLike]) -> bool:
    """Open a file or folder with the system default handler."""
    if not target:
        return False
    path = Path(target)
    if not path.exists():
        return False
    # QDesktopServices handles all three platforms and respects the user's
    # default application, unlike hand-rolled xdg-open/open/startfile calls.
    if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
        return True
    log.debug("QDesktopServices declined to open %s", path)
    return _open_fallback(path)


def _open_fallback(path: Path) -> bool:
    """Used when Qt has no usable handler, e.g. a bare X session with no
    xdg-utils and no MIME associations."""
    try:
        if sys.platform == "win32":
            import os

            os.startfile(str(path))  # noqa: S606 - the documented Windows API
            return True
        command = ["open"] if sys.platform == "darwin" else ["xdg-open"]
        subprocess.Popen([*command, str(path)], **_hidden_kwargs())
        return True
    except (OSError, AttributeError) as exc:
        log.debug("Fallback open failed for %s: %s", path, exc)
        return False


def reveal_path(target: Optional[PathLike]) -> bool:
    """Show a file in its containing folder, selected where supported.

    Qt has no API for this, so it needs per-platform commands. Falls back to
    simply opening the parent folder.
    """
    if not target:
        return False
    path = Path(target)
    if not path.exists():
        return False
    resolved = str(path.resolve())

    try:
        if sys.platform == "win32":
            # explorer returns exit code 1 even on success, so the return code
            # is deliberately not checked.
            subprocess.Popen(["explorer", f"/select,{resolved}"], **_hidden_kwargs())
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", resolved])
            return True

        # Linux: the FileManager1 D-Bus interface selects the file in Nautilus,
        # Dolphin, Nemo and Thunar. Not universal, hence the folder fallback.
        if _dbus_show_item(resolved):
            return True
    except OSError as exc:
        log.debug("Reveal failed for %s: %s", path, exc)

    parent = path.parent if path.is_file() else path
    return open_path(parent)


def _dbus_show_item(resolved: str) -> bool:
    try:
        result = subprocess.run(
            [
                "dbus-send",
                "--session",
                "--print-reply",
                "--dest=org.freedesktop.FileManager1",
                "--type=method_call",
                "/org/freedesktop/FileManager1",
                "org.freedesktop.FileManager1.ShowItems",
                f"array:string:file://{resolved}",
                "string:",
            ],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def containing_folder(target: Optional[PathLike]) -> Optional[Path]:
    """Nearest existing directory for a path that may itself be gone.

    Walks upward, so a deleted file inside a surviving album folder still opens
    somewhere useful rather than failing outright.
    """
    if not target:
        return None
    path = Path(target)
    candidate = path if path.is_dir() else path.parent
    for _ in range(6):
        if candidate.is_dir():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None
