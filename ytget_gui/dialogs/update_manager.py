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
import html
import threading
import time
from urllib.parse import unquote, urlsplit
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
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
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
# Not part of the REST API, so not subject to its 60-requests/hour anonymous
# limit: it answers with a redirect to ".../releases/tag/<tag>".
GITHUB_LATEST_WEB = "https://github.com/{owner}/{repo}/releases/latest"
GITHUB_ASSET = "https://github.com/{owner}/{repo}/releases/download/{tag}/{name}"
PYPI_JSON = "https://pypi.org/pypi/{package}/json"

# (connect, read). A single 15 s figure applied to each phase separately and,
# with four tools checked one after another, an offline machine sat on
# "Checking..." for a minute or more.
REQUEST_TIMEOUT = (6, 12)
DOWNLOAD_TIMEOUT = (6, 20)

# Successful lookups are reused for a while so reopening the dialog does not
# burn the anonymous GitHub API quota. "Re-check all" bypasses it.
_CACHE_TTL_S = 600
_release_cache: Dict[Tuple[str, str], Tuple[float, str, Optional[Dict[str, str]]]] = {}
_cache_lock = threading.Lock()


class UpdateCheckError(Exception):
    """A check failure with a message fit for the user."""


def _friendly_network_error(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.ProxyError):
        return "Could not connect through the configured proxy."
    if isinstance(exc, requests.exceptions.SSLError):
        return "Secure connection failed (SSL). Check the certificate settings."
    if isinstance(exc, requests.exceptions.Timeout):
        return "Timed out \u2014 GitHub did not answer in time."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "No connection \u2014 you appear to be offline or GitHub is unreachable."
    return f"Network error: {exc}"


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


class UpdateChecker(QObject):
    """Looks up installed and latest versions without ever blocking the GUI.

    Runs on plain daemon threads, one per tool, so a slow or unreachable
    endpoint delays only its own row and closing the dialog never has to wait
    for a socket timeout (the old QThread had to be joined before the dialog
    could be destroyed, which is what froze the window when offline or
    rate-limited).
    """

    installed = Signal(str, str)              # key, installed version
    result = Signal(str, str, str, str)       # key, installed, latest, url
    failed = Signal(str, str)
    notice = Signal(str)
    done = Signal()

    def __init__(self, settings: AppSettings, *, use_cache: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._use_cache = use_cache
        self._stop = threading.Event()
        self._running = threading.Event()
        self._api_limited = threading.Event()
        self._notice_lock = threading.Lock()
        self._noticed: set = set()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = f"YTGet/{_version.__version__}"
        self._verify, _args, _env = ssl_utils.resolve_ssl_config(settings)
        if self._verify is False:
            self._verify = True  # Software update trust cannot be switched off.
        proxy = (getattr(settings, "PROXY_URL", "") or "").strip()
        if proxy:
            self._session.proxies.update({"http": proxy, "https": proxy})
        self._token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()

    # -- thread control ------------------------------------------------

    def start(self) -> None:
        self._running.set()
        threading.Thread(target=self._run, name="update-check", daemon=True).start()

    def isRunning(self) -> bool:  # noqa: N802 - mirrors the QThread API it replaced
        return self._running.is_set()

    def requestInterruption(self) -> None:  # noqa: N802
        self._stop.set()

    def isInterruptionRequested(self) -> bool:  # noqa: N802
        return self._stop.is_set()

    def _emit(self, signal, *args) -> None:
        if self._stop.is_set():
            return
        try:
            signal.emit(*args)
        except RuntimeError:
            # The dialog is gone; nothing left to report to.
            self._stop.set()

    def _notice_once(self, key: str, text: str) -> None:
        with self._notice_lock:
            if key in self._noticed:
                return
            self._noticed.add(key)
        self._emit(self.notice, text)

    def _run(self) -> None:
        threads = [
            threading.Thread(target=self._check_safe, args=(tool,), daemon=True,
                             name=f"update-check-{tool.key}")
            for tool in TOOLS
        ]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                while thread.is_alive() and not self._stop.is_set():
                    thread.join(0.25)
        finally:
            self._running.clear()
            if not self._stop.is_set():
                self._emit(self.done)
            try:
                self._session.close()
            except Exception:  # noqa: BLE001
                pass

    def _check_safe(self, tool: Tool) -> None:
        try:
            self._check(tool)
        except UpdateCheckError as exc:
            self._emit(self.failed, tool.key, str(exc))
        except requests.RequestException as exc:
            self._emit(self.failed, tool.key, _friendly_network_error(exc))
        except Exception as exc:  # noqa: BLE001 - a check must never kill the dialog
            log.exception("Update check crashed for %s", tool.key)
            self._emit(self.failed, tool.key, str(exc))

    # -- lookups -------------------------------------------------------

    def _get(self, url: str, **kwargs):
        return self._session.get(url, timeout=REQUEST_TIMEOUT, verify=self._verify, **kwargs)

    def _latest_release(self, owner: str, repo: str) -> Tuple[str, str, Optional[Dict[str, str]]]:
        """(version, raw tag, {asset name: url} or None when unknown)."""
        cache_key = (owner.lower(), repo.lower())
        if self._use_cache:
            with _cache_lock:
                cached = _release_cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < _CACHE_TTL_S and cached[2] is not None:
                tag, assets = cached[1], cached[2]
                return tag.lstrip("v"), tag, assets

        if not self._api_limited.is_set():
            headers = {"Accept": "application/vnd.github+json"}
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            response = self._get(GITHUB_LATEST.format(owner=owner, repo=repo), headers=headers)
            if response.status_code in (403, 429) and (
                response.headers.get("X-RateLimit-Remaining") == "0"
                or "rate limit" in response.text.lower()
            ):
                self._api_limited.set()
                reset = response.headers.get("X-RateLimit-Reset", "")
                when = ""
                if reset.isdigit():
                    when = " until " + time.strftime("%H:%M", time.localtime(int(reset)))
                self._notice_once(
                    "rate",
                    f"GitHub API rate limit reached{when}; using the release pages instead.",
                )
            else:
                response.raise_for_status()
                payload = response.json()
                tag = str(payload.get("tag_name", ""))
                assets = {
                    str(a.get("name", "")): str(a.get("browser_download_url", ""))
                    for a in payload.get("assets", []) or []
                }
                with _cache_lock:
                    _release_cache[cache_key] = (time.monotonic(), tag, assets)
                return tag.lstrip("v"), tag, assets

        # Fallback: the web redirect is not API-limited.
        response = self._get(
            GITHUB_LATEST_WEB.format(owner=owner, repo=repo), allow_redirects=False
        )
        location = response.headers.get("Location", "")
        response.close()
        match = re.search(r"/releases/tag/([^/?#]+)/?$", location)
        if not match:
            if response.status_code in (403, 429):
                raise UpdateCheckError("GitHub is rate-limiting this network; try again later.")
            raise UpdateCheckError("Could not determine the latest release.")
        tag = unquote(match.group(1))
        return tag.lstrip("v"), tag, None

    def _pypi_latest(self, package: str) -> str:
        response = self._get(PYPI_JSON.format(package=package))
        response.raise_for_status()
        return str(response.json()["info"]["version"])

    @staticmethod
    def _asset_url(assets: Dict[str, str], predicate) -> str:
        return next((url for name, url in assets.items() if predicate(name)), "")

    def _check(self, tool: Tool) -> None:
        # Local probe first, so the row shows what is installed even when the
        # network lookup fails.
        current = installed_version(tool.key, self.settings)
        self._emit(self.installed, tool.key, current)
        if self._stop.is_set():
            return

        if tool.key == "spotdl" and not is_windows():
            self._emit(self.result, tool.key, current, self._pypi_latest(tool.package), "pip")
            return

        latest, tag, assets = self._latest_release(tool.owner, tool.repo)
        if self._stop.is_set():
            return

        def asset(name: str) -> str:
            if assets is not None:
                return assets.get(name, "")
            return GITHUB_ASSET.format(owner=tool.owner, repo=tool.repo, tag=tag, name=name)

        if tool.key == "ytget":
            url = f"https://github.com/{tool.owner}/{tool.repo}/releases/latest"
        elif tool.key == "yt-dlp":
            url = asset(ytdlp_asset_name())
        elif tool.key == "deno":
            url = asset(deno_asset_name())
        elif tool.key == "spotdl":
            # The standalone binary the app actually runs; names are
            # version-stamped, e.g. "spotdl-4.5.0-win32.exe".
            if assets is not None:
                url = self._asset_url(
                    assets, lambda n: n.startswith("spotdl-") and n.endswith("win32.exe")
                )
            else:
                url = asset(f"spotdl-{latest}-win32.exe")
        else:
            url = ""
        self._emit(self.result, tool.key, current, latest, url)


# ----------------------------------------------------------------------
# Installer
# ----------------------------------------------------------------------


class UpdateInstaller(QObject):
    """Downloads and installs one tool on a daemon thread.

    Not a QThread: a QThread must be joined before its owner is destroyed, so
    closing the dialog mid-download used to wait out the socket timeout.
    """

    progress = Signal(str, int)
    message = Signal(str, str)
    succeeded = Signal(str, str)   # key, new installed version
    failed = Signal(str, str)

    def __init__(self, key: str, url: str, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.key = key
        self.url = url
        self.settings = settings
        self._cancelled = False
        self._process = None
        self._running = threading.Event()
        self._detached = False

    def start(self) -> None:
        self._running.set()
        threading.Thread(target=self._run_guarded, name=f"install-{self.key}", daemon=True).start()

    def isRunning(self) -> bool:  # noqa: N802
        return self._running.is_set()

    def detach(self) -> None:
        """Stop reporting to the UI; the install itself finishes or cancels."""
        self._detached = True

    def cancel(self) -> None:
        self._cancelled = True
        threading.Thread(target=proc.terminate_tree, args=(self._process,), daemon=True).start()

    def _run_guarded(self) -> None:
        try:
            self.run()
        finally:
            self._running.clear()

    def _signal(self, signal, *args) -> None:
        if self._detached:
            return
        try:
            signal.emit(*args)
        except RuntimeError:
            self._detached = True

    def _succeed(self) -> None:
        version = installed_version(self.key, self.settings)
        # Persist here, not in the dialog: the dialog may already be closed.
        try:
            self.settings.save_config()
        except Exception:  # noqa: BLE001
            log.debug("Could not save config after install", exc_info=True)
        self._signal(self.succeeded, self.key, version)

    # ------------------------------------------------------------------

    def _log(self, text: str) -> None:
        self._signal(self.message, self.key, text)

    def _target_path(self) -> Path:
        """Private managed binaries: never replace a system executable."""
        base = self.settings.DATA_DIR / "bin"
        base.mkdir(parents=True, exist_ok=True)
        return base / executable_name(self.key)

    def _download(self, url: str, destination: Path) -> bool:
        verify, _args, _env = ssl_utils.resolve_ssl_config(self.settings)
        if verify is False:
            verify = True
        parsed = urlsplit(url)
        repos = {"yt-dlp": "/yt-dlp/yt-dlp/", "deno": "/denoland/deno/",
                 "spotdl": "/spotDL/spotify-downloader/"}
        if (parsed.scheme != "https" or parsed.hostname != "github.com"
                or not parsed.path.startswith(repos.get(self.key, "INVALID") + "releases/download/")):
            self._log("Refusing software download outside the official HTTPS release repository.")
            return False
        proxies = None
        proxy = (getattr(self.settings, "PROXY_URL", "") or "").strip()
        if proxy:
            proxies = {"http": proxy, "https": proxy}

        try:
            with requests.get(
                url, stream=True, timeout=DOWNLOAD_TIMEOUT,
                verify=verify, proxies=proxies,
                headers={"User-Agent": f"YTGet/{_version.__version__}"},
            ) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length") or 0)
                written = 0
                last_percent = -1
                with open(destination, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=65536):
                        if self._cancelled:
                            return False
                        if not chunk:
                            continue
                        handle.write(chunk)
                        written += len(chunk)
                        if total:
                            percent = int(written * 100 / total)
                            if percent != last_percent:  # one signal per percent, not per chunk
                                last_percent = percent
                                self._signal(self.progress, self.key, percent)
            return written > 0 and (not total or written == total) and not self._cancelled
        except requests.RequestException as exc:
            self._log(f"Download failed: {_friendly_network_error(exc)}")
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
                self._signal(self.failed, self.key, "Download cancelled or failed.")
                return

            self._log("Installing\u2026")
            self._make_executable(temp_path)
            if self._cancelled:
                self._signal(self.failed, self.key, "Cancelled.")
                return
            os.replace(temp_path, destination)
            if self.key == "yt-dlp":
                self.settings.YT_DLP_PATH = destination
            temp_path = None
            self._log("Done.")
            self._succeed()
        except OSError as exc:
            self._signal(self.failed, 
                self.key,
                f"{exc}. If the file is in use, close any running download first.",
            )
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _install_deno(self) -> None:
        final = self._target_path()
        destination_dir = final.parent
        self._log("Downloading Deno\u2026")
        handle, temp_name = tempfile.mkstemp(suffix=".zip", dir=str(destination_dir))
        os.close(handle)
        archive = Path(temp_name)

        try:
            if not self._download(self.url, archive):
                self._signal(self.failed, self.key, "Download cancelled or failed.")
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
                    self._signal(self.failed, self.key, "No deno binary inside the archive.")
                    return
                entry = bundle.getinfo(member)
                if entry.file_size > 512 * 1024 * 1024:
                    raise OSError("Deno archive exceeds the supported size limit")
                fd, staged_name = tempfile.mkstemp(dir=destination_dir, prefix=".deno-")
                staged = Path(staged_name)
                try:
                    with os.fdopen(fd, "wb") as target, bundle.open(member) as source:
                        shutil.copyfileobj(source, target)
                    self._make_executable(staged)
                    if self._cancelled:
                        raise OSError("Cancelled")
                    os.replace(staged, final)
                finally:
                    staged.unlink(missing_ok=True)

            self._make_executable(final)
            self.settings.DENO_PATH = final
            self._log("Done.")
            self._succeed()
        except (OSError, zipfile.BadZipFile) as exc:
            self._signal(self.failed, self.key, str(exc))
        finally:
            archive.unlink(missing_ok=True)

    def _install_spotdl(self) -> None:
        if self.url and self.url != "pip":
            self._install_binary(self._target_path())
            return

        if is_frozen():
            self._signal(self.failed, 
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
            self._process = process
            if self._cancelled:
                proc.terminate_tree(process)
            assert process.stdout is not None
            for raw in process.stdout:
                if self._cancelled:
                    proc.terminate_tree(process)
                    self._signal(self.failed, self.key, "Cancelled.")
                    return
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._log(line)
            code = process.wait()
            process.stdout.close()
            self._process = None
        except (OSError, subprocess.SubprocessError) as exc:
            self._signal(self.failed, self.key, str(exc))
            return

        if code == 0:
            self._log("Done.")
            self._succeed()
        else:
            self._signal(self.failed, self.key, f"pip exited with code {code}")

    def run(self) -> None:
        try:
            if self.key == "deno":
                self._install_deno()
            elif self.key == "spotdl":
                self._install_spotdl()
            elif self.key == "yt-dlp":
                self._install_binary(self._target_path())
            else:
                self._signal(self.failed, self.key, f"No installer for {self.key}.")
        except Exception as exc:  # noqa: BLE001 - a thread must not die silently
            log.exception("Installer crashed")
            self._signal(self.failed, self.key, str(exc))


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
        # Otherwise every opening leaves a dead dialog parented to the window.
        self.setAttribute(Qt.WA_DeleteOnClose, True)
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
        self.recheck_button.clicked.connect(lambda: self._check_all(use_cache=False))
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
        prefix = html.escape(f"[{label.label}] " if label else "")
        text = html.escape(text)
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

    def _check_all(self, use_cache: bool = True) -> None:
        if (self._checker is not None and self._checker.isRunning()) or any(i.isRunning() for i in self._installers.values()):
            return
        for key, row in self._rows.items():
            self._set_badge(key, "checking")
            row["button"].setEnabled(False)
            row["latest"].setText("latest: \u2014")
            row["progress"].hide()
            row["progress"].setValue(0)

        self.recheck_button.setEnabled(False)
        self.log_view.clear()
        self._log("", "Checking for updates\u2026")

        self._release_checker()
        # No Qt parent: the checker's threads may outlive this dialog.
        self._checker = UpdateChecker(self.settings, use_cache=use_cache)
        self._checker.installed.connect(self._on_installed_version)
        self._checker.result.connect(self._on_result)
        self._checker.failed.connect(self._on_check_failed)
        self._checker.notice.connect(self._on_notice)
        self._checker.done.connect(self._on_check_done)
        self._checker.start()

    def _release_checker(self) -> None:
        checker, self._checker = self._checker, None
        if checker is None:
            return
        checker.requestInterruption()
        for signal in (checker.installed, checker.result, checker.failed,
                       checker.notice, checker.done):
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass

    @Slot(str, str)
    def _on_installed_version(self, key: str, current: str) -> None:
        row = self._rows.get(key)
        if row is not None:
            row["installed"].setText(f"installed: {current}")

    @Slot(str)
    def _on_notice(self, text: str) -> None:
        self._log("", text, Palette.WARNING)

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
        row = self._rows.get(key)
        if row is not None:
            row["latest"].setText("latest: unavailable")
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

        installer = UpdateInstaller(key, url, self.settings)
        installer.progress.connect(self._on_progress)
        installer.message.connect(self._on_install_message)
        installer.succeeded.connect(self._on_installed)
        installer.failed.connect(self._on_install_failed)
        self._installers[key] = installer
        installer.start()

    @Slot(str, int)
    def _on_progress(self, key: str, percent: int) -> None:
        row = self._rows.get(key)
        if row is not None:
            row["progress"].setValue(percent)

    @Slot(str, str)
    def _on_install_message(self, key: str, text: str) -> None:
        self._log(key, text, Palette.ACCENT)

    @Slot(str, str)
    def _on_installed(self, key: str, version: str) -> None:
        # The version probe ran on the installer thread: spotdl --version alone
        # can take many seconds, and it used to run here on the GUI thread.
        row = self._rows.get(key)
        if row is not None:
            row["progress"].setValue(100)
            QTimer.singleShot(800, row["progress"].hide)
            self._set_badge(key, "done")
            row["installed"].setText(f"installed: {version}")
        self._log(key, "Installed successfully.", Palette.SUCCESS)

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
        """Detach from all background work. Never waits: nothing here blocks
        on a network call, so closing is instant even when offline."""
        self._release_checker()
        for installer in self._installers.values():
            for signal in (installer.progress, installer.message,
                           installer.succeeded, installer.failed):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass
            installer.detach()
            if installer.isRunning():
                installer.cancel()
        self._installers.clear()

    def closeEvent(self, event) -> None:
        self._stop_threads()
        super().closeEvent(event)

    def reject(self) -> None:
        self._stop_threads()
        super().reject()
