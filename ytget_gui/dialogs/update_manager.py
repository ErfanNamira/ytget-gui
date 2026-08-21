# File: ytget_gui/dialogs/update_manager.py
"""Update manager for the bundled tools.

Checks and installs:
  YTGet   - opens the GitHub release page (no in-app self-update)
  yt-dlp  - single binary from GitHub releases
  spotdl  - standalone binary on Windows, pip elsewhere
  deno    - zip archive from GitHub releases
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import webbrowser
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PySide6.QtCore import QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ytget_gui import _version
from ytget_gui.dialogs import common as ui
from ytget_gui.settings import AppSettings
from ytget_gui.styles import Palette
from ytget_gui.utils.paths import executable_name, is_frozen, is_windows, platform_label
from ytget_gui.workers import proc, ssl_utils

log = logging.getLogger(__name__)

GITHUB_LATEST = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
PYPI_JSON = "https://pypi.org/pypi/{package}/json"

REQUEST_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 120


@dataclass(frozen=True)
class Tool:
    key: str
    label: str
    icon: str
    owner: str = ""
    repo: str = ""
    package: str = ""


TOOLS: Tuple[Tool, ...] = (
    Tool("ytget", "YTGet", "\U0001f680", _version.GITHUB_OWNER, _version.GITHUB_REPO),
    Tool("yt-dlp", "yt-dlp", "\U0001f4e5", "yt-dlp", "yt-dlp"),
    Tool("spotdl", "spotDL", "\U0001f3b5", "spotDL", "spotify-downloader", "spotdl"),
    Tool("deno", "Deno", "\U0001f995", "denoland", "deno"),
)

_BADGES: Dict[str, Tuple[str, str]] = {
    "checking": (
        f"background: rgba(255,255,255,25); color: {Palette.TEXT_MUTED};", "Checking\u2026"
    ),
    "current": (
        f"background: rgba(34,211,165,30); color: {Palette.SUCCESS}; "
        "border: 1px solid rgba(34,211,165,60);", "Up to date"
    ),
    "available": (
        f"background: rgba(0,229,255,30); color: {Palette.ACCENT}; "
        "border: 1px solid rgba(0,229,255,60);", "Update available"
    ),
    "installing": (
        f"background: rgba(0,229,255,30); color: {Palette.ACCENT}; "
        "border: 1px solid rgba(0,229,255,60);", "Installing\u2026"
    ),
    "done": (
        f"background: rgba(34,211,165,30); color: {Palette.SUCCESS}; "
        "border: 1px solid rgba(34,211,165,60);", "Updated"
    ),
    "error": (
        f"background: rgba(248,113,113,30); color: {Palette.ERROR}; "
        "border: 1px solid rgba(248,113,113,60);", "Error"
    ),
    "missing": (
        f"background: rgba(251,191,36,28); color: {Palette.WARNING}; "
        "border: 1px solid rgba(251,191,36,70);", "Not installed"
    ),
}


# ----------------------------------------------------------------------
# Version helpers
# ----------------------------------------------------------------------


def parse_version(text: str) -> Tuple[Any, ...]:
    cleaned = (text or "").strip().lstrip("vn").split("+")[0].split("-")[0]
    parts: List[Any] = []
    for chunk in cleaned.split("."):
        try:
            parts.append((0, int(chunk)))
        except ValueError:
            parts.append((1, chunk))
    return tuple(parts)


def is_up_to_date(installed: str, latest: str) -> bool:
    """True when `installed` is at least `latest`.

    Unknown or missing installs are never "up to date", so the Update button
    stays available rather than silently disabling itself.
    """
    if not installed or not latest or installed in ("unknown", "not found"):
        return False
    try:
        return parse_version(installed) >= parse_version(latest)
    except TypeError:
        return installed == latest


def installed_version(key: str, settings: AppSettings) -> str:
    try:
        if key == "ytget":
            return _version.__version__

        if key == "yt-dlp":
            if not Path(settings.YT_DLP_PATH).is_file():
                return "not found"
            return proc.run([str(settings.YT_DLP_PATH), "--version"], timeout=10).stdout.strip()

        if key == "deno":
            if not Path(settings.DENO_PATH).is_file():
                return "not found"
            output = proc.run([str(settings.DENO_PATH), "--version"], timeout=10).stdout
            match = re.search(r"deno\s+([\d.]+)", output)
            return match.group(1) if match else "unknown"

        if key == "spotdl":
            from ytget_gui.workers.spotdl_worker import _find_spotdl

            binary = _find_spotdl(settings)
            if binary is None:
                return "not found"
            result = proc.run([str(binary), "--version"], timeout=20)
            output = result.stdout.strip() or result.stderr.strip()
            match = re.search(r"(\d+\.\d+\.\d+)", output)
            return match.group(1) if match else (output or "unknown")
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("Version probe failed for %s: %s", key, exc)
    return "not found"


def ytdlp_asset_name() -> str:
    if is_windows():
        return "yt-dlp.exe"
    machine = os.uname().machine.lower() if hasattr(os, "uname") else "x86_64"
    if sys.platform == "darwin":
        return "yt-dlp_macos" if machine in ("arm64", "aarch64") else "yt-dlp_macos_legacy"
    if machine in ("aarch64", "arm64"):
        return "yt-dlp_linux_aarch64"
    if machine.startswith("arm"):
        return "yt-dlp_linux_armv7l"
    return "yt-dlp_linux"


def deno_asset_name() -> str:
    machine = os.uname().machine.lower() if hasattr(os, "uname") else "x86_64"
    arch = "aarch64" if machine in ("aarch64", "arm64") else "x86_64"
    if is_windows():
        return "deno-x86_64-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return f"deno-{arch}-apple-darwin.zip"
    return f"deno-{arch}-unknown-linux-gnu.zip"


# ----------------------------------------------------------------------
# Checker
# ----------------------------------------------------------------------


class UpdateChecker(QThread):
    result = Signal(str, str, str, str)  # key, installed, latest, url
    failed = Signal(str, str)

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._session = requests.Session()
        self._session.headers["User-Agent"] = f"YTGet/{_version.__version__}"
        self._verify, _args, _env = ssl_utils.resolve_ssl_config(settings)
        ssl_utils.maybe_suppress_insecure_warning(self._verify)
        proxy = (getattr(settings, "PROXY_URL", "") or "").strip()
        if proxy:
            # The previous revision ignored the proxy entirely here, so update
            # checks failed on every proxied connection while downloads worked.
            self._session.proxies.update({"http": proxy, "https": proxy})

    def _latest_release(self, owner: str, repo: str) -> Tuple[str, List[dict]]:
        response = self._session.get(
            GITHUB_LATEST.format(owner=owner, repo=repo),
            timeout=REQUEST_TIMEOUT,
            verify=self._verify,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("tag_name", "")).lstrip("v"), payload.get("assets", [])

    def _pypi_latest(self, package: str) -> str:
        response = self._session.get(
            PYPI_JSON.format(package=package),
            timeout=REQUEST_TIMEOUT,
            verify=self._verify,
        )
        response.raise_for_status()
        return str(response.json()["info"]["version"])

    @staticmethod
    def _asset_url(assets: List[dict], predicate) -> str:
        return next(
            (a["browser_download_url"] for a in assets if predicate(a.get("name", ""))),
            "",
        )

    def run(self) -> None:
        try:
            for tool in TOOLS:
                if self.isInterruptionRequested():
                    return
                try:
                    self._check(tool)
                except requests.RequestException as exc:
                    self.failed.emit(tool.key, f"Network error: {exc}")
                except Exception as exc:  # noqa: BLE001
                    self.failed.emit(tool.key, str(exc))
        finally:
            # Each re-check builds a new session; without closing it the
            # connection pool's sockets are only reclaimed by GC, leaking file
            # descriptors across a long session of manual re-checks.
            self._session.close()

    def _check(self, tool: Tool) -> None:
        current = installed_version(tool.key, self.settings)

        if tool.key == "ytget":
            latest, _assets = self._latest_release(tool.owner, tool.repo)
            self.result.emit(
                tool.key, current, latest,
                f"https://github.com/{tool.owner}/{tool.repo}/releases/latest",
            )
            return

        if tool.key == "yt-dlp":
            latest, assets = self._latest_release(tool.owner, tool.repo)
            wanted = ytdlp_asset_name()
            self.result.emit(
                tool.key, current, latest,
                self._asset_url(assets, lambda n: n == wanted),
            )
            return

        if tool.key == "deno":
            latest, assets = self._latest_release(tool.owner, tool.repo)
            wanted = deno_asset_name()
            self.result.emit(
                tool.key, current, latest,
                self._asset_url(assets, lambda n: n == wanted),
            )
            return

        if tool.key == "spotdl":
            if is_windows():
                # Match the standalone binary the app actually runs, not the
                # pip package. Asset names are version-stamped, e.g.
                # "spotdl-4.5.0-win32.exe".
                latest, assets = self._latest_release(tool.owner, tool.repo)
                url = self._asset_url(
                    assets,
                    lambda n: n.startswith("spotdl-") and n.endswith("win32.exe"),
                )
                self.result.emit(tool.key, current, latest, url)
            else:
                self.result.emit(
                    tool.key, current, self._pypi_latest(tool.package), "pip"
                )


# ----------------------------------------------------------------------
# Installer
# ----------------------------------------------------------------------


class UpdateInstaller(QThread):
    progress = Signal(str, int)
    message = Signal(str, str)
    succeeded = Signal(str)
    failed = Signal(str, str)

    def __init__(self, key: str, url: str, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.key = key
        self.url = url
        self.settings = settings
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        self.requestInterruption()

    # ------------------------------------------------------------------

    def _log(self, text: str) -> None:
        self.message.emit(self.key, text)

    def _target_path(self) -> Path:
        """Prefer the path the app is configured to run.

        Installing to BASE_DIR unconditionally, as before, diverged from the
        configured path whenever a user pointed YTGet at a binary elsewhere:
        the update succeeded and the app kept running the old one.
        """
        base = self.settings.BASE_DIR
        if self.key == "yt-dlp":
            configured = getattr(self.settings, "YT_DLP_PATH", None)
            return Path(configured) if configured else base / executable_name("yt-dlp")
        if self.key == "deno":
            configured = getattr(self.settings, "DENO_PATH", None)
            return Path(configured) if configured else base / executable_name("deno")
        if self.key == "spotdl":
            from ytget_gui.workers.spotdl_worker import _find_spotdl

            found = _find_spotdl(self.settings)
            return Path(found) if found else base / executable_name("spotdl")
        return base

    def _download(self, url: str, destination: Path) -> bool:
        verify, _args, _env = ssl_utils.resolve_ssl_config(self.settings)
        ssl_utils.maybe_suppress_insecure_warning(verify)
        proxies = None
        proxy = (getattr(self.settings, "PROXY_URL", "") or "").strip()
        if proxy:
            proxies = {"http": proxy, "https": proxy}

        try:
            with requests.get(
                url, stream=True, timeout=DOWNLOAD_TIMEOUT,
                verify=verify, proxies=proxies,
            ) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length") or 0)
                written = 0
                with open(destination, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=65536):
                        if self._cancelled:
                            return False
                        if not chunk:
                            continue
                        handle.write(chunk)
                        written += len(chunk)
                        if total:
                            self.progress.emit(self.key, int(written * 100 / total))
            return written > 0
        except requests.RequestException as exc:
            self._log(f"Download failed: {exc}")
            return False
        except OSError as exc:
            self._log(f"Could not write the download: {exc}")
            return False

    @staticmethod
    def _make_executable(path: Path) -> None:
        if is_windows():
            return
        try:
            mode = os.stat(path).st_mode
            os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError as exc:
            log.debug("Could not chmod %s: %s", path, exc)

    def _install_binary(self, destination: Path) -> None:
        self._log(f"Downloading {self.key}\u2026")
        # mkstemp creates and opens atomically; mktemp only reserved a name,
        # which another process (or a concurrent installer) could claim first.
        handle, temp_name = tempfile.mkstemp(
            suffix=destination.suffix, dir=str(destination.parent)
        )
        os.close(handle)
        temp_path: Optional[Path] = Path(temp_name)

        try:
            if not self._download(self.url, temp_path):
                self.failed.emit(self.key, "Download cancelled or failed.")
                return

            self._log("Installing\u2026")
            self._make_executable(temp_path)
            try:
                os.replace(temp_path, destination)
            except OSError:
                # Windows refuses to replace a running executable; shutil.move
                # via a copy is the usual fallback.
                shutil.move(str(temp_path), str(destination))
            temp_path = None
            self._log("Done.")
            self.succeeded.emit(self.key)
        except OSError as exc:
            self.failed.emit(
                self.key,
                f"{exc}. If the file is in use, close any running download first.",
            )
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _install_deno(self) -> None:
        destination_dir = self.settings.BASE_DIR
        self._log("Downloading Deno\u2026")
        handle, temp_name = tempfile.mkstemp(suffix=".zip", dir=str(destination_dir))
        os.close(handle)
        archive = Path(temp_name)

        try:
            if not self._download(self.url, archive):
                self.failed.emit(self.key, "Download cancelled or failed.")
                return

            self._log("Extracting\u2026")
            final = destination_dir / executable_name("deno")
            with zipfile.ZipFile(archive) as bundle:
                member = next(
                    (
                        name
                        for name in bundle.namelist()
                        # Reject absolute paths and traversal: a malicious or
                        # malformed archive could otherwise write outside the
                        # target directory.
                        if re.fullmatch(r"deno(\.exe)?", os.path.basename(name), re.I)
                        and not os.path.isabs(name)
                        and ".." not in Path(name).parts
                    ),
                    None,
                )
                if member is None:
                    self.failed.emit(self.key, "No deno binary inside the archive.")
                    return
                with bundle.open(member) as source, open(final, "wb") as target:
                    shutil.copyfileobj(source, target)

            self._make_executable(final)
            self.settings.DENO_PATH = final
            self._log("Done.")
            self.succeeded.emit(self.key)
        except (OSError, zipfile.BadZipFile) as exc:
            self.failed.emit(self.key, str(exc))
        finally:
            archive.unlink(missing_ok=True)

    def _install_spotdl(self) -> None:
        if self.url and self.url != "pip":
            self._install_binary(self._target_path())
            return

        if is_frozen():
            self.failed.emit(
                self.key,
                "No standalone spotdl build exists for this platform, and pip "
                "is not available inside the packaged app. Install spotdl in a "
                "Python environment, or place the binary next to YTGet.",
            )
            return

        self._log("Running: pip install --upgrade spotdl")
        try:
            process = proc.spawn(
                [sys.executable, "-m", "pip", "install", "--upgrade", "spotdl"],
                own_process_group=True,
            )
            assert process.stdout is not None
            for raw in process.stdout:
                if self._cancelled:
                    proc.terminate_tree(process)
                    self.failed.emit(self.key, "Cancelled.")
                    return
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._log(line)
            code = process.wait()
        except (OSError, subprocess.SubprocessError) as exc:
            self.failed.emit(self.key, str(exc))
            return

        if code == 0:
            self._log("Done.")
            self.succeeded.emit(self.key)
        else:
            self.failed.emit(self.key, f"pip exited with code {code}")

    def run(self) -> None:
        try:
            if self.key == "deno":
                self._install_deno()
            elif self.key == "spotdl":
                self._install_spotdl()
            elif self.key == "yt-dlp":
                self._install_binary(self._target_path())
            else:
                self.failed.emit(self.key, f"No installer for {self.key}.")
        except Exception as exc:  # noqa: BLE001 - a thread must not die silently
            log.exception("Installer crashed")
            self.failed.emit(self.key, str(exc))


# ----------------------------------------------------------------------
# Dialog
# ----------------------------------------------------------------------


class UpdateManager(QDialog):
    MAX_LOG_BLOCKS = 400

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._checker: Optional[UpdateChecker] = None
        self._installers: Dict[str, UpdateInstaller] = {}
        self._rows: Dict[str, Dict[str, Any]] = {}

        self.setWindowTitle(f"Update Manager \u2014 {_version.APP_NAME}")
        self.setModal(True)
        self.setMinimumSize(700, 580)
        self.setStyleSheet(ui.dialog_qss())

        self._build()
        self._check_all()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Update Manager")
        title.setObjectName("dlgTitle")
        subtitle = QLabel(f"{_version.APP_NAME} {_version.__version__}  \u00b7  {platform_label()}")
        subtitle.setObjectName("dlgSubtitle")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(subtitle)
        root.addLayout(header)
        root.addWidget(ui.divider())

        scroll = QScrollArea()
        scroll.setObjectName("scrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self._rows_layout = QVBoxLayout(holder)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        for tool in TOOLS:
            self._add_row(tool)
        self._rows_layout.addStretch(1)
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

        root.addWidget(ui.divider())

        self.log_view = QTextEdit(readOnly=True)
        self.log_view.setFixedHeight(120)
        self.log_view.setStyleSheet(
            f"background: rgba(5,5,15,200); color: {Palette.TEXT_MUTED};"
            f"border: 1px solid {Palette.DIVIDER}; border-radius: 8px;"
            f"font-family: {Palette.MONO_FONTS}; font-size: 11px; padding: 8px;"
        )
        root.addWidget(self.log_view)

        footer = QHBoxLayout()
        self.recheck_button = QPushButton("Re-check all")
        self.recheck_button.clicked.connect(self._check_all)
        close_button = QPushButton("Close")
        close_button.setDefault(True)
        close_button.clicked.connect(self.reject)
        footer.addWidget(self.recheck_button)
        footer.addStretch(1)
        footer.addWidget(close_button)
        root.addLayout(footer)

    def _add_row(self, tool: Tool) -> None:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        icon = QLabel(tool.icon)
        icon.setFixedWidth(32)
        icon.setStyleSheet("font-size: 22px; background: transparent;")
        layout.addWidget(icon)

        column = QVBoxLayout()
        column.setSpacing(2)
        name = QLabel(tool.label)
        name.setObjectName("cardTitle")
        current = QLabel("installed: \u2014")
        current.setObjectName("cardSubtitle")
        latest = QLabel("latest: \u2014")
        latest.setObjectName("cardSubtitle")
        column.addWidget(name)
        column.addWidget(current)
        column.addWidget(latest)
        layout.addLayout(column, 1)

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setFixedWidth(120)
        progress.setTextVisible(False)
        progress.hide()
        layout.addWidget(progress)

        badge = QLabel()
        badge.setMinimumWidth(130)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet("border-radius: 6px; padding: 3px 10px; font-size: 11px;")
        layout.addWidget(badge)

        button = QPushButton("Update")
        button.setFixedWidth(96)
        button.setEnabled(False)
        button.clicked.connect(lambda _checked=False, key=tool.key: self._install(key))
        layout.addWidget(button)

        self._rows_layout.addWidget(frame)
        self._rows[tool.key] = {
            "tool": tool,
            "installed": current,
            "latest": latest,
            "badge": badge,
            "button": button,
            "progress": progress,
            "url": "",
        }
        self._set_badge(tool.key, "checking")

    def _set_badge(self, key: str, state: str) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        style, text = _BADGES.get(state, ("", state))
        row["badge"].setStyleSheet(
            f"{style} border-radius: 6px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
        )
        row["badge"].setText(text)

    def _log(self, key: str, text: str, colour: str = Palette.TEXT_MUTED) -> None:
        label = self._rows.get(key, {}).get("tool")
        prefix = f"[{label.label}] " if label else ""
        self.log_view.append(
            f'<span style="color:{Palette.TEXT_FAINT}">{prefix}</span>'
            f'<span style="color:{colour}">{text}</span>'
        )
        self.log_view.moveCursor(QTextCursor.End)

        # Trim from the top: only the tail is ever read, and an unbounded
        # document grows for the whole session.
        document = self.log_view.document()
        excess = document.blockCount() - self.MAX_LOG_BLOCKS
        if excess > 0:
            cursor = QTextCursor(document)
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, excess)
            cursor.removeSelectedText()

    # ------------------------------------------------------------------

    def _check_all(self) -> None:
        for key, row in self._rows.items():
            self._set_badge(key, "checking")
            row["button"].setEnabled(False)
            row["latest"].setText("latest: \u2014")
            row["progress"].hide()
            row["progress"].setValue(0)

        self.recheck_button.setEnabled(False)
        self.log_view.clear()
        self._log("", "Checking for updates\u2026")

        if self._checker is not None and self._checker.isRunning():
            self._checker.requestInterruption()
            self._checker.wait(3000)

        self._checker = UpdateChecker(self.settings, self)
        self._checker.result.connect(self._on_result)
        self._checker.failed.connect(self._on_check_failed)
        self._checker.finished.connect(self._on_check_done)
        self._checker.start()

    @Slot(str, str, str, str)
    def _on_result(self, key: str, current: str, latest: str, url: str) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        row["url"] = url
        row["installed"].setText(f"installed: {current}")
        row["latest"].setText(f"latest: {latest}")

        if key == "ytget":
            if is_up_to_date(current, latest):
                self._set_badge(key, "current")
            else:
                self._set_badge(key, "available")
                row["button"].setText("Open \u2197")
                row["button"].setEnabled(True)
            return

        if current == "not found":
            self._set_badge(key, "missing")
            row["button"].setText("Install")
            row["button"].setEnabled(bool(url))
            return

        if is_up_to_date(current, latest):
            self._set_badge(key, "current")
            row["button"].setEnabled(False)
        else:
            self._set_badge(key, "available")
            row["button"].setEnabled(bool(url))

    @Slot(str, str)
    def _on_check_failed(self, key: str, message: str) -> None:
        self._set_badge(key, "error")
        self._log(key, message, Palette.WARNING)

    @Slot()
    def _on_check_done(self) -> None:
        self.recheck_button.setEnabled(True)
        self._log("", "Check complete.")

    # ------------------------------------------------------------------

    def _install(self, key: str) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        url = row["url"]

        if key == "ytget":
            webbrowser.open(url)
            return

        existing = self._installers.get(key)
        if existing is not None and existing.isRunning():
            return

        row["button"].setEnabled(False)
        row["progress"].setValue(0)
        row["progress"].show()
        self._set_badge(key, "installing")

        installer = UpdateInstaller(key, url, self.settings, self)
        installer.progress.connect(self._on_progress)
        installer.message.connect(lambda k, m: self._log(k, m, Palette.ACCENT))
        installer.succeeded.connect(self._on_installed)
        installer.failed.connect(self._on_install_failed)
        self._installers[key] = installer
        installer.start()

    @Slot(str, int)
    def _on_progress(self, key: str, percent: int) -> None:
        row = self._rows.get(key)
        if row is not None:
            row["progress"].setValue(percent)

    @Slot(str)
    def _on_installed(self, key: str) -> None:
        row = self._rows.get(key)
        if row is not None:
            row["progress"].setValue(100)
            QTimer.singleShot(800, row["progress"].hide)
            self._set_badge(key, "done")
            row["installed"].setText(
                f"installed: {installed_version(key, self.settings)}"
            )
        self._log(key, "Installed successfully.", Palette.SUCCESS)
        self.settings.save_config()

    @Slot(str, str)
    def _on_install_failed(self, key: str, reason: str) -> None:
        row = self._rows.get(key)
        if row is not None:
            row["progress"].hide()
            self._set_badge(key, "error")
            row["button"].setEnabled(True)
        self._log(key, reason, Palette.ERROR)

    # ------------------------------------------------------------------

    def _stop_threads(self) -> None:
        if self._checker is not None and self._checker.isRunning():
            self._checker.requestInterruption()
            self._checker.wait(2000)
        for installer in self._installers.values():
            if installer.isRunning():
                installer.cancel()
                installer.wait(3000)

    def closeEvent(self, event) -> None:
        self._stop_threads()
        super().closeEvent(event)

    def reject(self) -> None:
        self._stop_threads()
        super().reject()
