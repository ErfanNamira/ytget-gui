# File: ytget_gui/dialogs/update_manager.py
from __future__ import annotations

import os
import sys
import shutil
import tempfile
import subprocess
import platform
from pathlib import Path

import requests
from packaging import version
from PySide6.QtCore import QObject, Signal

from ytget_gui.styles import AppStyles
from ytget_gui.utils.paths import is_windows


class UpdateManager(QObject):
    """
    Thread-safe update manager for ytget_gui and yt-dlp.

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

    # ytget_gui update results
    ytget_gui_ready = Signal(str)        # latest version
    ytget_gui_uptodate = Signal()        # already up to date
    ytget_gui_error = Signal(str)        # error message

    # yt-dlp update results
    ytdlp_ready = Signal(str, str, str)  # latest, current, asset_url
    ytdlp_uptodate = Signal(str)         # current version
    ytdlp_error = Signal(str)            # error message

    # yt-dlp download outcome
    ytdlp_download_success = Signal()
    ytdlp_download_failed = Signal(str)  # error message

    def __init__(self, settings: Any, log_callback=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._log_cb = log_callback

        # Determine GitHub owner/repo from settings.GITHUB_URL
        owner_repo = "/".join(self.settings.GITHUB_URL.rstrip("/").split("/")[-2:])
        self.ytget_gui_api = f"https://api.github.com/repos/{owner_repo}/releases/latest"
        self.ytdlp_api = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

        # HTTP session with optional proxy
        self.session = requests.Session()
        if getattr(self.settings, "PROXY_URL", ""):
            self.session.proxies.update({
                "http": self.settings.PROXY_URL,
                "https": self.settings.PROXY_URL,
                "socks5": self.settings.PROXY_URL,
            })

    # -------- Public entry points --------

    def check_all_updates(self):
        """Check both ytget_gui and yt-dlp updates sequentially."""
        self.check_ytget_gui_update()
        self.check_ytdlp_update()

    def check_ytget_gui_update(self):
        """Check if a newer ytget_gui release is available."""
        self._log("🌐 Checking for YTGet updates...\n", AppStyles.INFO_COLOR, "Info")
        try:
            latest = self._fetch_latest_version(self.ytget_gui_api)
            if version.parse(latest) > version.parse(self.settings.VERSION):
                self.ytget_gui_ready.emit(latest)
            else:
                self.ytget_gui_uptodate.emit()
        except Exception as e:
            self.ytget_gui_error.emit(str(e))

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

    def _select_ytdlp_asset(self, assets: list) -> Optional[dict]:
        """
        Pick the correct yt-dlp binary asset name based on OS:
          - Windows: yt-dlp.exe
          - macOS: look for macOS Intel or Universal2 build, fallback to generic
          - Linux/others: yt-dlp
        """
        sysname = platform.system().lower()
        if sysname.startswith("win"):
            candidates = ["yt-dlp.exe"]
        elif sysname == "darwin":
            candidates = ["yt-dlp_macos", "yt-dlp_macos_universal2", "yt-dlp"]
        else:
            candidates = ["yt-dlp"]

        for name in candidates:
            for a in assets:
                if a.get("name") == name:
                    return a
        return None

    def _get_ytdlp_version(self, exe_path: Path) -> str | None:
        """Return version string if binary exists and runs, else None."""
        if not exe_path.exists():
            return None
        try:
            kwargs: dict[str, Any] = {}
            if platform.system().lower().startswith("win"):
                # suppress console window on Windows
                try:
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                except AttributeError:
                    pass

            result = subprocess.run(
                [str(exe_path), "--version"],
                capture_output=True,
                text=True,
                timeout=6,
                **kwargs
            )
            out = (result.stdout or "").strip()
            return out or None
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