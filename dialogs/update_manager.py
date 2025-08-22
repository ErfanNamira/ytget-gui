# File: ytget/dialogs/update_manager.py
from __future__ import annotations

import os
import sys
import shutil
import tempfile
import subprocess
import webbrowser
from pathlib import Path

import requests
from packaging import version
from PySide6.QtWidgets import QMessageBox

from ytget.styles import AppStyles
from ytget.utils.paths import is_windows


class UpdateManager:
    """
    Handles update checks and updates for:
      - YTGet (app): opens latest release page
      - yt-dlp (dependency): downloads and replaces the local binary
    """

    def __init__(self, settings, log_callback=None, parent=None):
        """
        :param settings: AppSettings instance
        :param log_callback: callable(text, color, level) -> None
        :param parent: QWidget (for dialogs)
        """
        self.settings = settings
        self.log = log_callback or (lambda *a, **k: None)
        self.parent = parent

        # APIs
        owner_repo = "/".join(self.settings.GITHUB_URL.rstrip("/").split("/")[-2:])
        self.ytget_api = f"https://api.github.com/repos/{owner_repo}/releases/latest"
        self.ytdlp_api = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

        # Optional proxy
        self.session = requests.Session()
        if getattr(self.settings, "PROXY_URL", ""):
            self.session.proxies.update({"http": self.settings.PROXY_URL, "https": self.settings.PROXY_URL})

    # -------- Public entry points --------

    def check_all_updates(self):
        """Check YTGet and yt-dlp sequentially."""
        self.check_ytget_update()
        self.check_ytdlp_update()

    def check_ytget_update(self):
        """Check YTGet release; offer to open the Releases page."""
        self.log("🌐 Checking for YTGet updates...\n", AppStyles.INFO_COLOR, "Info")
        try:
            r = self.session.get(self.ytget_api, timeout=10)
            r.raise_for_status()
            data = r.json()
            latest = (data.get("tag_name") or "").lstrip("v")
            if not latest:
                raise ValueError("Missing release tag_name")
            if version.parse(latest) > version.parse(self.settings.VERSION):
                reply = QMessageBox.information(
                    self.parent,
                    f"{self.settings.APP_NAME} Update Available",
                    f"A new version ({latest}) is available.\n"
                    f"You are using {self.settings.VERSION}.\n\n"
                    "Open the releases page?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    webbrowser.open(f"{self.settings.GITHUB_URL}/releases/latest")
            else:
                QMessageBox.information(self.parent, "Up to Date", f"{self.settings.APP_NAME} is up to date.")
        except Exception as e:
            QMessageBox.warning(self.parent, "Update Check Failed", f"Could not check {self.settings.APP_NAME} updates:\n{e}")

    def check_ytdlp_update(self):
        """Check yt-dlp; offer to download and replace the local binary."""
        self.log("🌐 Checking for yt-dlp updates...\n", AppStyles.INFO_COLOR, "Info")
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

            current_ver = self._get_ytdlp_version(exe_path) if exe_path.exists() else "0.0.0"
            if version.parse(latest) > version.parse(current_ver):
                reply = QMessageBox.question(
                    self.parent,
                    "yt-dlp Update Available",
                    f"A new yt-dlp version ({latest}) is available.\n"
                    f"Current version: {current_ver}\n\n"
                    "Download and replace it now?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._download_and_replace(asset["browser_download_url"], exe_path, label="yt-dlp")
            else:
                QMessageBox.information(self.parent, "Up to Date", "yt-dlp is up to date.")
        except Exception as e:
            QMessageBox.warning(self.parent, "yt-dlp Update Check Failed", f"Could not check yt-dlp updates:\n{e}")

    # -------- Internal helpers --------

    def _select_ytdlp_asset(self, assets):
        """
        Pick the correct yt-dlp asset based on the platform.
        - Windows: yt-dlp.exe
        - macOS: yt-dlp_macos (prefer unzipped binary)
        - Linux/Other POSIX: yt-dlp
        """
        names = [a.get("name", "") for a in assets]
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

    def _get_ytdlp_version(self, exe_path: Path) -> str:
        try:
            result = subprocess.run([str(exe_path), "--version"], capture_output=True, text=True, timeout=6)
            out = (result.stdout or "").strip()
            return out if out else "0.0.0"
        except Exception:
            return "0.0.0"

    def _download_and_replace(self, url: str, dest_path: Path, label: str):
        try:
            self.log(f"⬇️ Downloading latest {label}...\n", AppStyles.INFO_COLOR, "Info")
            with self.session.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                fd, tmp_path = tempfile.mkstemp(suffix=Path(url).suffix or "")
                with os.fdopen(fd, "wb") as tmp_file:
                    shutil.copyfileobj(r.raw, tmp_file)

            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # On Windows, replacing an in-use file can fail; try a best-effort
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

            self.log(f"✅ {label} updated successfully.\n", AppStyles.SUCCESS_COLOR, "Info")
            QMessageBox.information(self.parent, f"{label} Updated", f"{label} has been updated successfully.")
        except Exception as e:
            QMessageBox.critical(self.parent, f"{label} Update Failed", f"Could not update {label}:\n{e}")
