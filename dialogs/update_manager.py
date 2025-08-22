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
    Thread-safe update manager for YTGet and yt-dlp.

    Responsibilities:
    - Check for updates via GitHub API
    - Download and replace binaries
    - Emit signals for UI to handle dialogs and progress
    - Never touch UI directly (safe for QThread use)
    """

    # Logging to UI console: text, color, level
    log_signal = Signal(str, str, str)

    # Progress updates: percent (0-100), label
    progress_signal = Signal(int, str)

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
        self._log_cb = log_callback  # kept for compatibility

        # API endpoints
        owner_repo = "/".join(self.settings.GITHUB_URL.rstrip("/").split("/")[-2:])
        self.ytget_api = f"https://api.github.com/repos/{owner_repo}/releases/latest"
        self.ytdlp_api = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

        # HTTP session with optional proxy
        self.session = requests.Session()
        if getattr(self.settings, "PROXY_URL", ""):
            self.session.proxies.update({
                "http": self.settings.PROXY_URL,
                "https": self.settings.PROXY_URL
            })

    # -------- Public entry points --------

    def check_all_updates(self):
        """Check both YTGet and yt-dlp updates sequentially."""
        self.check_ytget_update()
        self.check_ytdlp_update()

    def check_ytget_update(self):
        """Check if a newer YTGet release is available."""
        self._log("🌐 Checking for YTGet updates...\n", AppStyles.INFO_COLOR, "Info")
        try:
            latest = self._fetch_latest_version(self.ytget_api)
            if version.parse(latest) > version.parse(self.settings.VERSION):
                self.ytget_ready.emit(latest)
            else:
                self.ytget_uptodate.emit()
        except Exception as e:
            self.ytget_error.emit(str(e))

    def check_ytdlp_update(self):
        """Check if a newer yt-dlp release is available."""
        self._log("🌐 Checking for yt-dlp updates...\n", AppStyles.INFO_COLOR, "Info")
        exe_path = Path(self.settings.YT_DLP_PATH)

        try:
            latest, asset_url = self._fetch_latest_ytdlp_info()
            current_ver = self._get_ytdlp_version(exe_path)

            if not current_ver:
                self.ytdlp_ready.emit(latest, "Not installed", asset_url)
                return

            if version.parse(latest) > version.parse(current_ver):
                self.ytdlp_ready.emit(latest, current_ver, asset_url)
            else:
                self.ytdlp_uptodate.emit(current_ver)
        except Exception as e:
            self.ytdlp_error.emit(str(e))

    def download_ytdlp(self, url: str):
        """Download and replace yt-dlp binary."""
        try:
            exe_path = Path(self.settings.YT_DLP_PATH)
            self._download_with_progress(url, exe_path, label="yt-dlp")
            self._log("✅ yt-dlp updated successfully.\n", AppStyles.SUCCESS_COLOR, "Info")
            self.ytdlp_download_success.emit()
        except Exception as e:
            self.ytdlp_download_failed.emit(str(e))

    # -------- Internal helpers --------

    def _fetch_latest_version(self, api_url: str) -> str:
        r = self.session.get(api_url, timeout=10)
        r.raise_for_status()
        data = r.json()
        latest = (data.get("tag_name") or "").lstrip("v")
        if not latest:
            raise ValueError("Missing release tag_name")
        return latest

    def _fetch_latest_ytdlp_info(self) -> tuple[str, str]:
        r = self.session.get(self.ytdlp_api, timeout=10)
        r.raise_for_status()
        data = r.json()
        latest = (data.get("tag_name") or "").lstrip("v")
        assets = data.get("assets") or []
        asset = self._select_ytdlp_asset(assets)
        if not asset:
            raise ValueError("No suitable yt-dlp binary found for this platform.")
        return latest, asset["browser_download_url"]

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
        """Return version string if binary exists and runs, else None."""
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

    def _download_with_progress(self, url: str, dest_path: Path, label: str):
        """Download file with progress updates."""
        self._log(f"⬇️ Downloading latest {label}...\n", AppStyles.INFO_COLOR, "Info")
        with self.session.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            fd, tmp_path = tempfile.mkstemp(suffix=Path(url).suffix or "")
            with os.fdopen(fd, "wb") as tmp_file:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            percent = int(downloaded * 100 / total)
                            self.progress_signal.emit(percent, label)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.exists():
            try:
                os.remove(dest_path)
            except Exception:
                pass
        shutil.move(tmp_path, dest_path)

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
