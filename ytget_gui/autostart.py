# File: ytget_gui/autostart.py
"""Run-on-login registration, per platform.

Three backends, one interface:

- Windows: an HKCU \\...\\CurrentVersion\\Run value. HKCU, not HKLM, because
  HKLM needs admin rights and would launch for every account on the machine.
- macOS: a LaunchAgent plist with RunAtLoad.
- Linux/BSD: an XDG autostart .desktop file.

The launch delay is passed to the app as --delay instead of being expressed in
the platform entry, because only launchd can express a delay natively, so
doing it in-process is the only behaviour that is identical everywhere.

Every function reports success as a bool and never raises: failing to register
autostart must not stop Preferences from saving.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from ytget_gui import _version
from ytget_gui.utils.paths import is_frozen, is_macos, is_windows

log = logging.getLogger(__name__)

ENTRY_NAME = _version.APP_NAME
_BUNDLE_ID = "com.ytget.autostart"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command(minimized: bool, delay: int) -> List[str]:
    """Argv that starts YTGet the same way the current process was started."""
    if is_frozen():
        argv = [str(Path(sys.executable).resolve())]
    else:
        # -m keeps working if the package is moved, unlike a path to main.py.
        argv = [str(Path(sys.executable).resolve()), "-m", "ytget_gui"]
    if minimized:
        argv.append("--minimized")
    if delay > 0:
        argv += ["--delay", str(int(delay))]
    return argv


def _quote(argv: List[str]) -> str:
    if is_windows():
        return " ".join(f'"{part}"' if " " in part else part for part in argv)
    return " ".join(shlex.quote(part) for part in argv)


# ----------------------------------------------------------------------
# Windows
# ----------------------------------------------------------------------


def _win_set(enabled: bool, argv: List[str]) -> Tuple[bool, str]:
    import winreg  # noqa: PLC0415 - Windows only

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, ENTRY_NAME, 0, winreg.REG_SZ, _quote(argv))
            else:
                try:
                    winreg.DeleteValue(key, ENTRY_NAME)
                except FileNotFoundError:
                    pass
        return True, ""
    except OSError as exc:
        return False, str(exc)


def _win_get() -> bool:
    import winreg  # noqa: PLC0415 - Windows only

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, ENTRY_NAME)
            return True
    except OSError:
        return False


# ----------------------------------------------------------------------
# macOS
# ----------------------------------------------------------------------


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_BUNDLE_ID}.plist"


def _mac_set(enabled: bool, argv: List[str]) -> Tuple[bool, str]:
    path = _plist_path()
    try:
        if not enabled:
            if path.exists():
                subprocess.run(
                    ["launchctl", "unload", str(path)],
                    check=False,
                    capture_output=True,
                )
                path.unlink()
            return True, ""

        path.parent.mkdir(parents=True, exist_ok=True)
        args = "".join(f"        <string>{part}</string>\n" for part in argv)
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            "    <key>Label</key>\n"
            f"    <string>{_BUNDLE_ID}</string>\n"
            "    <key>ProgramArguments</key>\n"
            "    <array>\n"
            f"{args}"
            "    </array>\n"
            "    <key>RunAtLoad</key>\n"
            "    <true/>\n"
            "    <key>ProcessType</key>\n"
            "    <string>Interactive</string>\n"
            "</dict>\n"
            "</plist>\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["launchctl", "load", str(path)], check=False, capture_output=True
        )
        return True, ""
    except OSError as exc:
        return False, str(exc)


# ----------------------------------------------------------------------
# Linux / BSD
# ----------------------------------------------------------------------


def _desktop_path() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config) / "autostart" / "ytget.desktop"


def _linux_set(enabled: bool, argv: List[str]) -> Tuple[bool, str]:
    path = _desktop_path()
    try:
        if not enabled:
            if path.exists():
                path.unlink()
            return True, ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={ENTRY_NAME}\n"
            "Comment=Start YTGet when you log in\n"
            f"Exec={_quote(argv)}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n",
            encoding="utf-8",
        )
        return True, ""
    except OSError as exc:
        return False, str(exc)


# ----------------------------------------------------------------------
# Public interface
# ----------------------------------------------------------------------


def is_enabled() -> bool:
    """True when an autostart entry currently exists."""
    try:
        if is_windows():
            return _win_get()
        if is_macos():
            return _plist_path().exists()
        return _desktop_path().exists()
    except Exception:  # noqa: BLE001 - probing must never raise
        log.debug("Could not probe autostart state", exc_info=True)
        return False


def apply(enabled: bool, minimized: bool = True, delay: int = 30) -> Tuple[bool, str]:
    """Create or remove the autostart entry.

    Returns (ok, error_message). Rewritten rather than patched when already
    enabled, so changes to the delay or the minimised flag take effect.
    """
    argv = launch_command(minimized, delay)
    try:
        if is_windows():
            return _win_set(enabled, argv)
        if is_macos():
            return _mac_set(enabled, argv)
        return _linux_set(enabled, argv)
    except Exception as exc:  # noqa: BLE001 - never block a settings save
        log.exception("Autostart update failed")
        return False, str(exc)


def location() -> Optional[str]:
    """Where the entry lives, for display in Preferences."""
    if is_windows():
        return f"HKCU\\{_RUN_KEY}\\{ENTRY_NAME}"
    if is_macos():
        return str(_plist_path())
    return str(_desktop_path())
