# File: ytget_gui/dialogs/update_manager.py

"""
Cross-platform Update Manager for YTGet.

Handles checking and updating:
  • YTGet                — GitHub Releases (ErfanNamira/ytget-gui)
  • yt-dlp               — GitHub Releases (yt-dlp/yt-dlp)
  • SpotDL               — GitHub Releases (spotDL/spotify-downloader) on Windows,
                            matching the standalone spotdl.exe the app actually
                            uses (see workers/spotdl_worker.py); falls back to
                            `pip install --upgrade spotdl` elsewhere
  • Deno                 — GitHub Releases (denoland/deno)

Architecture
────────────
  UpdateChecker  (QThread)  — fetches latest versions via GitHub API / pip index
  UpdateInstaller(QThread)  — downloads & installs a single tool
  UpdateManager  (QDialog)  — the UI; owns one checker and N installer threads
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from PySide6.QtCore import (
    Qt, QThread, QTimer, Signal, Slot, QSize,
)
from PySide6.QtGui import QColor, QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

# ── helpers imported from the app ──────────────────────────────────────────
from ytget_gui.utils.paths import is_windows, executable_name
from ytget_gui.settings import AppSettings

# ═══════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

GITHUB_API          = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
GITHUB_RELEASES_API = "https://api.github.com/repos/{owner}/{repo}/releases"
PYPI_API            = "https://pypi.org/pypi/{package}/json"

TOOLS: Dict[str, Dict[str, Any]] = {
    "ytget": {
        "label":   "YTGet GUI",
        "owner":   "ErfanNamira",
        "repo":    "ytget-gui",
        "kind":    "ytget",
        "icon":    "🚀",
    },
    "yt-dlp": {
        "label":   "yt-dlp",
        "owner":   "yt-dlp",
        "repo":    "yt-dlp",
        "kind":    "github_binary",
        "icon":    "📥",
    },
    "spotdl": {
        "label":   "SpotDL",
        "owner":   "spotDL",
        "repo":    "spotify-downloader",
        "package": "spotdl",
        "kind":    "github_binary_or_pip",
        "icon":    "🎵",
    },
    "deno": {
        "label":   "Deno",
        "owner":   "denoland",
        "repo":    "deno",
        "kind":    "github_binary",
        "icon":    "🦕",
    },
}

REQUEST_TIMEOUT = 15   # seconds

# Prevent a console/terminal window from flashing up when we spawn helper
# processes (yt-dlp --version, deno --version, pip, etc.) on Windows.
_POPEN_KWARGS: Dict[str, Any] = {}
if sys.platform == "win32":
    _POPEN_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW
    _startupinfo = subprocess.STARTUPINFO()
    _startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _startupinfo.wShowWindow = subprocess.SW_HIDE
    _POPEN_KWARGS["startupinfo"] = _startupinfo

# ═══════════════════════════════════════════════════════════════════════════
#  PLATFORM HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _system() -> str:
    return platform.system().lower()

def _machine() -> str:
    m = platform.machine().lower()
    if m in ("amd64", "x86_64"):
        return "x86_64"
    if m.startswith("aarch64") or m.startswith("arm64"):
        return "aarch64"
    return m

def _current_version(tool_key: str, settings: AppSettings) -> str:
    """Try to read the installed version for a tool."""
    try:
        if tool_key == "ytget":
            return settings.VERSION

        if tool_key == "yt-dlp":
            result = subprocess.run(
                [str(settings.YT_DLP_PATH), "--version"],
                capture_output=True, text=True, timeout=8,
                **_POPEN_KWARGS,
            )
            return result.stdout.strip()

        if tool_key == "spotdl":
            # Resolve the same way workers/spotdl_worker.py does: a bundled
            # spotdl(.exe) next to the app, or one on PATH. `sys.executable`
            # is the frozen YTGet.exe itself in a packaged build, not a
            # Python interpreter, so `-m spotdl` only works when running
            # from source with spotdl installed as a pip package.
            from ytget_gui.workers.spotdl_worker import _find_spotdl
            spotdl_path = _find_spotdl(settings)
            if spotdl_path is None:
                return "not found"
            result = subprocess.run(
                [str(spotdl_path), "--version"],
                capture_output=True, text=True, timeout=10,
                **_POPEN_KWARGS,
            )
            out = (result.stdout.strip() or result.stderr.strip())
            m = re.search(r"(\d+\.\d+\.\d+)", out)
            return m.group(1) if m else (out or "unknown")

        if tool_key == "deno":
            result = subprocess.run(
                [str(settings.DENO_PATH), "--version"],
                capture_output=True, text=True, timeout=8,
                **_POPEN_KWARGS,
            )
            # "deno 2.x.y\n..."
            m = re.search(r"deno\s+([\d.]+)", result.stdout)
            return m.group(1) if m else "unknown"

    except Exception:
        pass
    return "not found"


def _asset_name_for_ytdlp() -> str:
    """Return the correct yt-dlp binary asset name for this platform."""
    if is_windows():
        return "yt-dlp.exe"
    sys_ = _system()
    mach = _machine()
    if sys_ == "linux":
        return "yt-dlp_linux" if mach == "x86_64" else f"yt-dlp_linux_{mach}"
    if sys_ == "darwin":
        return "yt-dlp_macos" if mach == "aarch64" else "yt-dlp_macos_legacy"
    return "yt-dlp"


def _asset_name_for_deno(tag: str) -> str:
    """Return the correct Deno asset name for this platform."""
    sys_ = _system()
    mach = _machine()
    if is_windows():
        return "deno-x86_64-pc-windows-msvc.zip"
    if sys_ == "darwin":
        arch = "aarch64" if mach == "aarch64" else "x86_64"
        return f"deno-{arch}-apple-darwin.zip"
    # linux
    arch = "aarch64" if mach == "aarch64" else "x86_64"
    return f"deno-{arch}-unknown-linux-gnu.zip"


# ═══════════════════════════════════════════════════════════════════════════
#  UPDATE CHECKER
# ═══════════════════════════════════════════════════════════════════════════

class UpdateChecker(QThread):
    """
    Emits result_ready(tool_key, installed_version, latest_version, download_url)
    for each tool, then finished() when all checks are done.
    """

    result_ready = Signal(str, str, str, str)   # key, installed, latest, url
    error        = Signal(str, str)             # key, message

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._session  = requests.Session()
        self._session.headers["User-Agent"] = f"YTGet/{settings.VERSION}"

    # ── internal helpers ───────────────────────────────────────────────────

    def _gh_latest(self, owner: str, repo: str) -> Tuple[str, List[dict]]:
        """Fetch the single latest release (may include pre-releases/nightlies)."""
        url  = GITHUB_API.format(owner=owner, repo=repo)
        resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        tag  = data.get("tag_name", "").lstrip("v")
        return tag, data.get("assets", [])

    def _pip_latest(self, package: str) -> str:
        url  = PYPI_API.format(package=package)
        resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["info"]["version"]

    # ── per-tool check methods ─────────────────────────────────────────────

    def _check_ytget(self):
        key = "ytget"
        installed = _current_version(key, self._settings)
        try:
            latest, _assets = self._gh_latest("ErfanNamira", "ytget-gui")
            # find the release page URL (no direct binary; user visits GitHub)
            dl_url = f"https://github.com/ErfanNamira/ytget-gui/releases/tag/{latest}"
            self.result_ready.emit(key, installed, latest, dl_url)
        except Exception as e:
            self.error.emit(key, str(e))

    def _check_ytdlp(self):
        key = "yt-dlp"
        installed = _current_version(key, self._settings)
        try:
            latest, assets = self._gh_latest("yt-dlp", "yt-dlp")
            asset_name = _asset_name_for_ytdlp()
            dl_url = next(
                (a["browser_download_url"] for a in assets if a["name"] == asset_name),
                "",
            )
            self.result_ready.emit(key, installed, latest, dl_url)
        except Exception as e:
            self.error.emit(key, str(e))

    def _check_spotdl(self):
        key = "spotdl"
        installed = _current_version(key, self._settings)
        try:
            if is_windows():
                # Match the standalone binary the app actually runs
                # (see release.yml / workers/spotdl_worker.py), not the
                # pip package. Asset name is version-stamped, e.g.
                # "spotdl-4.5.0-win32.exe", so match by prefix/suffix.
                latest, assets = self._gh_latest("spotDL", "spotify-downloader")
                dl_url = next(
                    (
                        a["browser_download_url"] for a in assets
                        if a["name"].startswith("spotdl-") and a["name"].endswith("win32.exe")
                    ),
                    "",
                )
                self.result_ready.emit(key, installed, latest, dl_url)
            else:
                # No standalone binary is published for macOS/Linux; spotdl
                # is expected to be installed via pip there.
                latest = self._pip_latest("spotdl")
                self.result_ready.emit(key, installed, latest, "pip")
        except Exception as e:
            self.error.emit(key, str(e))

    def _check_deno(self):
        key = "deno"
        installed = _current_version(key, self._settings)
        try:
            latest, assets = self._gh_latest("denoland", "deno")
            asset_name = _asset_name_for_deno(latest)
            dl_url = next(
                (a["browser_download_url"] for a in assets if a["name"] == asset_name),
                "",
            )
            self.result_ready.emit(key, installed, latest, dl_url)
        except Exception as e:
            self.error.emit(key, str(e))

    def run(self):
        try:
            for fn in (
                self._check_ytget,
                self._check_ytdlp,
                self._check_spotdl,
                self._check_deno,
            ):
                if self.isInterruptionRequested():
                    break
                try:
                    fn()
                except Exception:
                    pass   # individual errors already emitted inside each method
        finally:
            # Each "Re-check All" click spins up a brand new UpdateChecker
            # (and Session); without closing it, the underlying connection
            # pool's sockets are only reclaimed by GC, which leaks file
            # descriptors/memory over a long-running session with many
            # manual re-checks.
            self._session.close()


# ═══════════════════════════════════════════════════════════════════════════
#  UPDATE INSTALLER  (runs in a thread, one per tool)
# ═══════════════════════════════════════════════════════════════════════════

class UpdateInstaller(QThread):
    """
    Downloads and installs a single tool update.
    Signals:
      progress(tool_key, percent)    — 0..100
      log_line(tool_key, message)
      finished_ok(tool_key)
      finished_err(tool_key, reason)
    """

    progress     = Signal(str, int)
    log_line     = Signal(str, str)
    finished_ok  = Signal(str)
    finished_err = Signal(str, str)

    def __init__(
        self,
        tool_key: str,
        download_url: str,
        settings: AppSettings,
        parent=None,
    ):
        super().__init__(parent)
        self._key      = tool_key
        self._url      = download_url
        self._settings = settings
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.requestInterruption()

    # ── helpers ────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.log_line.emit(self._key, msg)

    def _download(self, url: str, dest: Path) -> bool:
        """Stream-download url to dest, emitting progress signals."""
        try:
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            done  = 0
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    if self._cancelled:
                        return False
                    fh.write(chunk)
                    done += len(chunk)
                    if total:
                        self.progress.emit(self._key, int(done * 100 / total))
            return True
        except Exception as exc:
            self._log(f"Download failed: {exc}")
            return False

    def _make_executable(self, path: Path):
        if not is_windows():
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def _install_path_for(self, tool_key: str) -> Path:
        """Where to write the updated binary.

        Prefer the path the app is *currently configured* to run (e.g.
        settings.YT_DLP_PATH), falling back to BASE_DIR only when that
        attribute is unset. Previously this always installed to
        BASE_DIR/<name>, which silently diverged from the configured path
        whenever the user pointed YTGet at a binary living elsewhere (a
        custom install, a system-wide yt-dlp, etc.) — the update would
        succeed but the app would keep running the old binary.
        """
        base = self._settings.BASE_DIR
        if tool_key == "yt-dlp":
            configured = getattr(self._settings, "YT_DLP_PATH", None)
            return Path(configured) if configured else base / executable_name("yt-dlp")
        if tool_key == "deno":
            configured = getattr(self._settings, "DENO_PATH", None)
            return Path(configured) if configured else base / executable_name("deno")
        if tool_key == "spotdl":
            try:
                from ytget_gui.workers.spotdl_worker import _find_spotdl
                found = _find_spotdl(self._settings)
                if found is not None:
                    return Path(found)
            except Exception:
                pass
            return base / executable_name("spotdl")
        return base

    # ── install strategies ─────────────────────────────────────────────────

    def _install_single_binary(self, tool_key: str, asset_url: str):
        dest = self._install_path_for(tool_key)
        self._log(f"Downloading {tool_key} …")
        # tempfile.mktemp only *reserves* a name; another process (or a
        # concurrent installer thread) can grab it before we open it. Using
        # mkstemp atomically creates and opens the file, closing the classic
        # race, and doubles as a guarantee the parent temp dir is writable
        # before we start streaming a potentially large download into it.
        fd, tmp_name = tempfile.mkstemp(suffix=dest.suffix)
        os.close(fd)
        tmp = Path(tmp_name)
        if not self._download(asset_url, tmp):
            self.finished_err.emit(tool_key, "Download cancelled or failed.")
            return
        self._log("Installing …")
        try:
            shutil.move(str(tmp), str(dest))
            self._make_executable(dest)
            self._log("✅ Done.")
            self.finished_ok.emit(tool_key)
        except Exception as exc:
            self.finished_err.emit(tool_key, str(exc))
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def _install_ytdlp(self):
        self._install_single_binary("yt-dlp", self._url)

    def _install_deno(self):
        """Download zip, extract deno binary, place in BASE_DIR."""
        dest_dir = self._settings.BASE_DIR
        self._log("Downloading Deno …")
        fd, tmp_zip_name = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        tmp_zip = Path(tmp_zip_name)
        if not self._download(self._url, tmp_zip):
            self.finished_err.emit("deno", "Download cancelled or failed.")
            return
        self._log("Extracting …")
        try:
            with zipfile.ZipFile(tmp_zip) as zf:
                # The archive contains a single 'deno' (or 'deno.exe') binary
                for member in zf.namelist():
                    if re.search(r"deno(\.exe)?$", member, re.IGNORECASE):
                        zf.extract(member, dest_dir)
                        extracted = dest_dir / member
                        final = dest_dir / executable_name("deno")
                        if extracted != final:
                            shutil.move(str(extracted), str(final))
                        self._make_executable(final)
                        self._settings.DENO_PATH = final
                        self._log("✅ Done.")
                        self.finished_ok.emit("deno")
                        return
            self.finished_err.emit("deno", "deno binary not found in archive.")
        except Exception as exc:
            self.finished_err.emit("deno", str(exc))
        finally:
            tmp_zip.unlink(missing_ok=True)

    def _install_spotdl(self):
        # Windows: a real download URL means the checker found a matching
        # spotdl-*.exe GitHub release asset — install it as a plain binary,
        # exactly like yt-dlp, so it lands next to the running app and is
        # picked up by workers/spotdl_worker.py's _find_spotdl().
        if self._url and self._url != "pip":
            self._install_single_binary("spotdl", self._url)
            return

        # Fallback: pip install (source runs, or platforms with no published
        # standalone binary). This won't work inside a frozen PyInstaller
        # build since sys.executable is YTGet.exe, not a Python interpreter —
        # surface a clear error instead of silently failing.
        if getattr(sys, "frozen", False):
            self.finished_err.emit(
                "spotdl",
                "No spotdl binary release found for this platform, and pip "
                "install isn't available inside the packaged app. Install "
                "spotdl manually and place it next to YTGet, or run "
                "'pip install spotdl' in a Python environment.",
            )
            return

        self._log("Running: pip install --upgrade spotdl …")
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "pip", "install", "--upgrade", "spotdl"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                **_POPEN_KWARGS,
            )
            for line in proc.stdout:
                if self._cancelled:
                    proc.kill()
                    self.finished_err.emit("spotdl", "Cancelled.")
                    return
                self._log(line.rstrip())
            proc.wait()
            if proc.returncode == 0:
                self._log("✅ Done.")
                self.finished_ok.emit("spotdl")
            else:
                self.finished_err.emit("spotdl", f"pip exited with code {proc.returncode}")
        except Exception as exc:
            self.finished_err.emit("spotdl", str(exc))

    def run(self):
        dispatch = {
            "yt-dlp":  self._install_ytdlp,
            "spotdl":  self._install_spotdl,
            "deno":    self._install_deno,
        }
        fn = dispatch.get(self._key)
        if fn:
            fn()
        else:
            self.finished_err.emit(self._key, f"No installer for '{self._key}'.")


# ═══════════════════════════════════════════════════════════════════════════
#  QSS  (mirrors app theme)
# ═══════════════════════════════════════════════════════════════════════════

_QSS = """
QDialog {
    background: #09090B;
    color: #E4E4E7;
    font-family: "JetBrains Mono", "Fira Code", Consolas, monospace;
    font-size: 13px;
}
QLabel { color: #E4E4E7; }
#Title {
    font-size: 16px;
    font-weight: 700;
    color: #00E5FF;
    letter-spacing: 1px;
}
#Subtitle {
    font-size: 11px;
    color: #52525B;
}
QFrame#Divider {
    background: #1E1E24;
    min-height: 1px;
    max-height: 1px;
}
/* ── Tool row ── */
QFrame#ToolRow {
    background: #111113;
    border: 1px solid #1E1E24;
    border-radius: 8px;
}
QFrame#ToolRow:hover {
    border-color: #2A2A34;
}
#ToolIcon  { font-size: 22px; }
#ToolLabel { font-weight: 700; font-size: 13px; color: #E4E4E7; }
#VersionInstalled { font-size: 11px; color: #52525B; }
#VersionLatest    { font-size: 11px; color: #00E5FF; }
#StatusBadge {
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}
/* ── Buttons ── */
QPushButton#BtnUpdate {
    background: #00E5FF;
    color: #09090B;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 700;
    font-size: 12px;
}
QPushButton#BtnUpdate:hover   { background: #33EEFF; }
QPushButton#BtnUpdate:disabled { background: #1A2E33; color: #3A5560; }
QPushButton#BtnRefresh {
    background: #141418;
    color: #A1A1AA;
    border: 1px solid #27272A;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
}
QPushButton#BtnRefresh:hover { color: #E4E4E7; border-color: #3F3F46; }
QPushButton#BtnClose {
    background: #141418;
    color: #A1A1AA;
    border: 1px solid #27272A;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
}
QPushButton#BtnClose:hover { color: #E4E4E7; border-color: #3F3F46; }
/* ── Log pane ── */
QTextEdit#LogPane {
    background: #070709;
    color: #52525B;
    border: 1px solid #1A1A20;
    border-radius: 6px;
    font-size: 11px;
    font-family: "JetBrains Mono", Consolas, monospace;
    padding: 6px;
}
/* ── Progress ── */
QProgressBar {
    background: #1A1A20;
    border: none;
    border-radius: 3px;
    height: 4px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: #00E5FF;
    border-radius: 3px;
}
/* ── Scroll ── */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: #09090B;
    width: 6px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #27272A;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #3F3F46; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

# ── status badge colours ────────────────────────────────────────────────────
_STATUS_STYLE = {
    "checking":  ("background:#1A1A20; color:#71717A;", "Checking…"),
    "up_to_date":("background:#14291A; color:#22C55E;", "Up to date"),
    "update":    ("background:#2A1818; color:#F87171;", "Update available"),
    "error":     ("background:#2A1A0A; color:#FB923C;", "Error"),
    "installing":("background:#1A1A20; color:#00E5FF;", "Installing…"),
    "done":      ("background:#14291A; color:#22C55E;", "Updated ✓"),
    "warning":   ("background:#2A1A0A; color:#FB923C;", "Manual update"),
}


# ═══════════════════════════════════════════════════════════════════════════
#  UPDATE MANAGER  (dialog)
# ═══════════════════════════════════════════════════════════════════════════

class UpdateManager(QDialog):
    """
    Main update-manager dialog.  Call UpdateManager(settings, parent).exec()
    """

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._checker: Optional[UpdateChecker] = None
        self._installers: Dict[str, UpdateInstaller] = {}

        # per-tool widget references
        self._rows: Dict[str, Dict[str, Any]] = {}

        self.setWindowTitle("Update Manager — YTGet")
        self.setMinimumSize(680, 560)
        self.setStyleSheet(_QSS)
        self._build_ui()
        self._start_check()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Update Manager")
        title.setObjectName("Title")
        subtitle = QLabel(f"YTGet {self.settings.VERSION}  ·  {platform.system()} {platform.release()}")
        subtitle.setObjectName("Subtitle")
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(subtitle)
        root.addLayout(hdr)

        divider = QFrame()
        divider.setObjectName("Divider")
        root.addWidget(divider)

        # Scrollable tool list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        self._tool_layout = QVBoxLayout(inner)
        self._tool_layout.setSpacing(8)
        self._tool_layout.setContentsMargins(0, 0, 0, 0)
        for key, meta in TOOLS.items():
            self._add_tool_row(key, meta)
        self._tool_layout.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        divider2 = QFrame()
        divider2.setObjectName("Divider")
        root.addWidget(divider2)

        # Log pane
        self._log = QTextEdit()
        self._log.setObjectName("LogPane")
        self._log.setReadOnly(True)
        self._log.setFixedHeight(110)
        root.addWidget(self._log)

        # Bottom buttons
        btn_row = QHBoxLayout()
        self._btn_refresh = QPushButton("🔄  Re-check All")
        self._btn_refresh.setObjectName("BtnRefresh")
        self._btn_refresh.clicked.connect(self._start_check)
        btn_row.addWidget(self._btn_refresh)
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setObjectName("BtnClose")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    def _add_tool_row(self, key: str, meta: dict):
        row_frame = QFrame()
        row_frame.setObjectName("ToolRow")
        row_layout = QHBoxLayout(row_frame)
        row_layout.setContentsMargins(14, 12, 14, 12)
        row_layout.setSpacing(12)

        # icon
        icon_lbl = QLabel(meta.get("icon", "🔧"))
        icon_lbl.setObjectName("ToolIcon")
        icon_lbl.setFixedWidth(32)
        row_layout.addWidget(icon_lbl)

        # name + versions column
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        name_lbl = QLabel(meta["label"])
        name_lbl.setObjectName("ToolLabel")
        ver_installed = QLabel("installed: —")
        ver_installed.setObjectName("VersionInstalled")
        ver_latest = QLabel("latest: —")
        ver_latest.setObjectName("VersionLatest")
        info_col.addWidget(name_lbl)
        info_col.addWidget(ver_installed)
        info_col.addWidget(ver_latest)
        row_layout.addLayout(info_col, stretch=1)

        # progress bar (hidden by default)
        prog = QProgressBar()
        prog.setRange(0, 100)
        prog.setValue(0)
        prog.setFixedWidth(120)
        prog.hide()
        row_layout.addWidget(prog)

        # status badge
        badge = QLabel("Checking…")
        badge.setObjectName("StatusBadge")
        badge.setMinimumWidth(120)
        badge.setAlignment(Qt.AlignCenter)
        self._set_badge(badge, "checking")
        row_layout.addWidget(badge)

        # update button
        btn = QPushButton("Update")
        btn.setObjectName("BtnUpdate")
        btn.setEnabled(False)
        btn.setFixedWidth(90)
        btn.clicked.connect(lambda checked=False, k=key: self._on_update(k))
        row_layout.addWidget(btn)

        self._tool_layout.addWidget(row_frame)

        self._rows[key] = {
            "frame":         row_frame,
            "ver_installed": ver_installed,
            "ver_latest":    ver_latest,
            "badge":         badge,
            "btn":           btn,
            "progress":      prog,
            "latest":        "",
            "url":           "",
        }

    # ── badge helper ───────────────────────────────────────────────────────

    def _set_badge(self, badge: QLabel, status_key: str):
        style, text = _STATUS_STYLE.get(status_key, ("", status_key))
        badge.setStyleSheet(style)
        badge.setText(text)

    # ── logging ────────────────────────────────────────────────────────────

    _MAX_LOG_BLOCKS = 500

    def _log_line(self, tool_key: str, msg: str, color: str = "#52525B"):
        label = TOOLS.get(tool_key, {}).get("label", tool_key)
        html  = (
            f'<span style="color:#3F3F46">[{label}]</span> '
            f'<span style="color:{color}">{msg}</span>'
        )
        self._log.append(html)
        self._log.moveCursor(QTextCursor.End)

        # Without a cap, a session left open through many manual re-checks
        # and installs accumulates an ever-growing QTextDocument (each
        # append also pushes an undo entry) for no user-visible benefit —
        # only the tail of the log is ever read. Trim from the top instead.
        doc = self._log.document()
        if doc.blockCount() > self._MAX_LOG_BLOCKS:
            cursor = QTextCursor(doc)
            cursor.movePosition(QTextCursor.Start)
            excess = doc.blockCount() - self._MAX_LOG_BLOCKS
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, excess)
            cursor.removeSelectedText()

    # ── check flow ─────────────────────────────────────────────────────────

    def _start_check(self):
        # Reset UI
        for key, row in self._rows.items():
            self._set_badge(row["badge"], "checking")
            row["btn"].setEnabled(False)
            row["ver_latest"].setText("latest: —")
            row["progress"].hide()
            row["progress"].setValue(0)
        self._btn_refresh.setEnabled(False)
        self._log.clear()
        self._log_line("", "Checking for updates…", "#71717A")

        if self._checker and self._checker.isRunning():
            self._checker.requestInterruption()
            self._checker.wait(3000)

        self._checker = UpdateChecker(self.settings, self)
        self._checker.result_ready.connect(self._on_check_result)
        self._checker.error.connect(self._on_check_error)
        self._checker.finished.connect(self._on_check_done)
        self._checker.start()

    @Slot(str, str, str, str)
    def _on_check_result(self, key: str, installed: str, latest: str, url: str):
        row = self._rows.get(key)
        if not row:
            return
        row["latest"] = latest
        row["url"]    = url
        row["ver_installed"].setText(f"installed: {installed}")
        row["ver_latest"].setText(f"latest: {latest}")

        if key == "ytget":
            # No in-app binary update for YTGet itself
            up_to_date = _versions_equal(installed, latest)
            if up_to_date:
                self._set_badge(row["badge"], "up_to_date")
            else:
                self._set_badge(row["badge"], "update")
                row["btn"].setText("GitHub ↗")
                row["btn"].setEnabled(True)
            return

        up_to_date = _versions_equal(installed, latest)
        if up_to_date:
            self._set_badge(row["badge"], "up_to_date")
            row["btn"].setEnabled(False)
        else:
            self._set_badge(row["badge"], "update")
            row["btn"].setEnabled(bool(url))

    @Slot(str, str)
    def _on_check_error(self, key: str, msg: str):
        row = self._rows.get(key)
        if row:
            self._set_badge(row["badge"], "error")
        self._log_line(key, f"Error: {msg}", "#FB923C")

    @Slot()
    def _on_check_done(self):
        self._btn_refresh.setEnabled(True)
        self._log_line("", "Check complete.", "#71717A")

    # ── install flow ───────────────────────────────────────────────────────

    def _on_update(self, key: str):
        row = self._rows.get(key)
        if not row:
            return
        url = row["url"]

        if key == "ytget":
            import webbrowser
            webbrowser.open(url)
            return

        # guard: don't start a second installer for the same tool
        if key in self._installers and self._installers[key].isRunning():
            return

        row["btn"].setEnabled(False)
        row["progress"].setValue(0)
        row["progress"].show()
        self._set_badge(row["badge"], "installing")

        installer = UpdateInstaller(key, url, self.settings, self)
        installer.progress.connect(self._on_progress)
        installer.log_line.connect(lambda k, m: self._log_line(k, m, "#00E5FF"))
        installer.finished_ok.connect(self._on_install_ok)
        installer.finished_err.connect(self._on_install_err)
        self._installers[key] = installer
        installer.start()

    @Slot(str, int)
    def _on_progress(self, key: str, pct: int):
        row = self._rows.get(key)
        if row:
            row["progress"].setValue(pct)

    @Slot(str)
    def _on_install_ok(self, key: str):
        row = self._rows.get(key)
        if row:
            row["progress"].setValue(100)
            QTimer.singleShot(800, row["progress"].hide)
            self._set_badge(row["badge"], "done")
            # refresh installed version label
            new_ver = _current_version(key, self.settings)
            row["ver_installed"].setText(f"installed: {new_ver}")
        self._log_line(key, "Update installed successfully.", "#22C55E")
        self.settings.save_config()

    @Slot(str, str)
    def _on_install_err(self, key: str, reason: str):
        row = self._rows.get(key)
        if row:
            row["progress"].hide()
            self._set_badge(row["badge"], "error")
            row["btn"].setEnabled(True)
        self._log_line(key, f"Install failed: {reason}", "#F87171")

    # ── cleanup ────────────────────────────────────────────────────────────

    def _stop_all_threads(self):
        """Cancel and wait for all running background threads."""
        if self._checker and self._checker.isRunning():
            self._checker.requestInterruption()
            self._checker.wait(2000)
        for inst in self._installers.values():
            if inst.isRunning():
                inst.cancel()
                inst.wait(3000)

    def closeEvent(self, event):
        self._stop_all_threads()
        super().closeEvent(event)

    def reject(self):
        self._stop_all_threads()
        super().reject()


# ═══════════════════════════════════════════════════════════════════════════
#  UTILITY
# ═══════════════════════════════════════════════════════════════════════════

def _versions_equal(a: str, b: str) -> bool:
    """
    Loose version comparison: strip leading 'v'/'n', compare normalised segments.
    Returns True when the installed version is considered equal or newer.
    """
    if not a or not b or a in ("unknown", "not found"):
        return False

    def _norm(v: str) -> tuple:
        # Strip leading 'v' or 'n' (BtbN uses 'n' prefix on stable tags)
        v = v.lstrip("vn").split("+")[0].split("-")[0]
        parts = []
        for x in v.split("."):
            try:
                parts.append((0, int(x)))   # (0, int) sorts before (1, str)
            except ValueError:
                parts.append((1, x))
        return tuple(parts)

    try:
        return _norm(a) >= _norm(b)
    except TypeError:
        # Last-resort: plain string comparison
        return a >= b
