# File: ytget/dialogs/update_manager.py
from __future__ import annotations

import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path

import requests
from packaging import version
from PySide6.QtCore import QObject, Signal

from ytget.styles import AppStyles
from ytget.utils.paths import is_windows


class UpdateManager(QObject):
    """
    Thread-friendly update manager:
      - Does NOT touch UI directly (no QMessageBox/webbrowser here)
      - Emits signals so the main thread can show dialogs
    """

    # Logging to UI console: text, color, level
    log_signal = Signal(str, str, str)

    # YTGet update results
    ytget_ready = Signal(str)           # latest version
    ytget_uptodate = Signal()           # already up to date
    ytget_error = Signal(str)           # error message

    # yt-dlp update results
    ytdlp_ready = Signal(str, str, str)  # latest, current, asset_url
    ytdlp_uptodate = Signal(str)         # current version
    ytdlp_error = Signal(str)            # error message

    # yt-dlp download outcome
    ytdlp_download_success = Signal()
    ytdlp_download_failed = Signal(str)  # error message

    def __init__(self, settings, log_callback=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._log_cb = log_callback

        # APIs
        owner_repo = "/".join(self.settings.GITHUB_URL.rstrip("/").split("/")[-2:])
        self.ytget_api = f"https://api.github.com/repos/{owner_repo}/releases/latest"
        self.ytdlp_api = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

        # Optional proxy
        self.session = requests.Session()
        if getattr(self.settings, "PROXY_URL", ""):
            self.session.proxies.update({
                "http": self.settings.PROXY_URL,
                "https": self.settings.PROXY_URL
            })

    # -------- Public entry points --------

    def check_all_updates(self):
        self.check_ytget_update()
        self.check_ytdlp_update()

    def check_ytget_update(self):
        self._log("🌐 Checking for YTGet updates...\n", AppStyles.INFO_COLOR, "Info")
        try:
            r = self.session.get(self.ytget_api, timeout=10)
            r.raise_for_status()
            data = r.json()
            latest = (data.get("tag_name") or "").lstrip("v")
            if not latest:
                raise ValueError("Missing release tag_name")
            if version.parse(latest) > version.parse(self.settings.VERSION):
                self.ytget_ready.emit(latest)
            else:
                self.ytget_uptodate.emit()
        except Exception as e:
            self.ytget_error.emit(str(e))

    def check_ytdlp_update(self):
        self._log("🌐 Checking for yt-dlp updates...\n", AppStyles.INFO_COLOR, "Info")
        exe_path = Path(self.settings.YT_DLP_PATH)

        try:
            r = self.session.get(self.ytdlp_api, timeout=10)
            r.raise_for_status()
            data = r.json()
            latest = (data.get("tag_name") or "").lstrip("v")
            assets = data.get("assets") or []
            asset = self._select_ytdlp_asset(assets)
            if not asset:
                raise ValueError("No suitable yt-dlp binary found for this platform.")

            current_ver = self._get_ytdlp_version(exe_path)

            if not current_ver:
                # No local yt-dlp at the expected path
                self.ytdlp_ready.emit(latest, "Not installed", asset["browser_download_url"])
                return

            if version.parse(latest) > version.parse(current_ver):
                self.ytdlp_ready.emit(latest, current_ver, asset["browser_download_url"])
            else:
                self.ytdlp_uptodate.emit(current_ver)
        except Exception as e:
            self.ytdlp_error.emit(str(e))

    def download_ytdlp(self, url: str):
        """
        Run in worker thread. Emits ytdlp_download_success / ytdlp_download_failed.
        """
        try:
            exe_path = Path(self.settings.YT_DLP_PATH)
            self._download_and_replace(url, exe_path, label="yt-dlp")
            self._log("✅ yt-dlp updated successfully.\n", AppStyles.SUCCESS_COLOR, "Info")
            self.ytdlp_download_success.emit()
        except Exception as e:
            self.ytdlp_download_failed.emit(str(e))

    # -------- Internal helpers (no UI) --------

    def _select_ytdlp_asset(self, assets):
        if is_windows():
            target_names = ["yt-dlp.exe"]
        elif sys.platform == "darwin":
            target_names = ["yt-dlp_macos", "yt-dlp"]
        else:
            target_names = ["yt-dlp"]

        for name in target_names:
            for a in assets:
                if a.get("name") == name:
                    return a
        return None

    def _get_ytdlp_version(self, exe_path: Path) -> str | None:
        """
        Returns the version string if the binary exists and runs successfully.
        Returns None if not installed or cannot be executed.
        """
        if not exe_path.exists():
            return None
        try:
            result = subprocess.run(
                [str(exe_path), "--version"],
                capture_output=True, text=True, timeout=6
            )
            out = (result.stdout or "").strip()
            return out if out else None
        except Exception:
            return None

    def _download_and_replace(self, url: str, dest_path: Path, label: str):
        self._log(f"⬇️ Downloading latest {label}...\n", AppStyles.INFO_COLOR, "Info")
        with self.session.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            fd, tmp_path = tempfile.mkstemp(suffix=Path(url).suffix or "")
            with os.fdopen(fd, "wb") as tmp_file:
                shutil.copyfileobj(r.raw, tmp_file)

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # On Windows, replacing an in-use file can fail; best-effort remove
        if dest_path.exists():
            try:
                os.remove(dest_path)
            except Exception:
                pass

        shutil.move(tmp_path, dest_path)

        # Ensure executable bit on POSIX
        if not is_windows():
            try:
                dest_path.chmod(0o755)
            except Exception:
                pass

    # -------- Logging helper --------

    def _log(self, text: str, color: str, level: str):
        try:
            self.log_signal.emit(text, color, level)
        except Exception:
            pass
