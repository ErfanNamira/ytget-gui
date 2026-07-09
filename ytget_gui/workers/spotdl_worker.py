# File: ytget_gui/workers/spotdl_worker.py

"""
Worker that runs a spotdl download command inside a QThread.

    worker.log      Signal(str, str)   – text chunk + colour
    worker.status   Signal(str)        – short progress text
    worker.finished Signal(int)        – exit code (0 = success)
    worker.error    Signal(str)        – error description

Usage
-----
    item = {"url": "https://open.spotify.com/...", "title": "My Playlist"}
    worker = SpotDLWorker(item, settings, spotdl_settings)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    ...
"""

from __future__ import annotations

import os
import platform
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal, QProcess, QTimer, QProcessEnvironment

from ytget_gui.styles import AppStyles
from ytget_gui.settings import AppSettings
from ytget_gui.spotdl_settings import SpotDLSettings


def _executable_name(base: str) -> str:
    """Return platform-correct binary name."""
    return f"{base}.exe" if os.name == "nt" else base


def _find_spotdl(app_settings: AppSettings) -> Optional[Path]:
    """
    Locate spotdl binary:
      1. BASE_DIR / spotdl[.exe]
      2. INTERNAL_DIR / spotdl[.exe]
      3. System PATH via shutil.which
    Returns None when not found.
    """
    from shutil import which

    candidates = [
        app_settings.BASE_DIR / _executable_name("spotdl"),
        app_settings.INTERNAL_DIR / _executable_name("spotdl"),
    ]
    for c in candidates:
        if c.exists():
            return c

    found = which("spotdl")
    return Path(found) if found else None


# ---------------------------------------------------------------------------
#  Worker
# ---------------------------------------------------------------------------

class SpotDLWorker(QObject):
    log = Signal(str, str)
    status = Signal(str)
    finished = Signal(int)
    error = Signal(str)

    def __init__(
        self,
        item: Dict[str, Any],
        app_settings: AppSettings,
        spotdl_settings: SpotDLSettings,
        log_flush_ms: int = 300,
        status_throttle_ms: int = 500,
    ):
        super().__init__()
        self.item = item
        self.app_settings = app_settings
        self.spotdl_settings = spotdl_settings

        self.process: Optional[QProcess] = None
        self._cancel_requested = False

        self._log_buffer: List[Tuple[str, str]] = []
        self._log_timer: Optional[QTimer] = None
        self._log_flush_ms = max(100, int(log_flush_ms))

        self._last_status_text: Optional[str] = None
        self._last_status_emit = 0.0
        self._status_throttle_s = max(0.05, status_throttle_ms / 1000.0)

        # Patterns for progress detection
        self._percent_re = re.compile(r"(\d{1,3})%")
        self._eta_re = re.compile(r"(\d+:\d+)\s*(?:remaining|left|eta)", re.IGNORECASE)

        # spotdl exits 0 even when individual tracks in a batch fail (e.g. an
        # AudioProviderError from yt-dlp on one provider). Track these so the
        # final status message isn't misleadingly "successful".
        self._track_error_re = re.compile(
            r"(AudioProviderError|LookupError:.*not found|Skipping .* \(as it is Explicit\))",
            re.IGNORECASE,
        )
        self._track_errors: List[str] = []

    # ------------------------------------------------------------------
    def run(self):
        try:
            if self._log_timer is None:
                self._log_timer = QTimer(self)
                self._log_timer.setInterval(self._log_flush_ms)
                self._log_timer.timeout.connect(self._flush_logs)
                self._log_timer.start()

            spotdl_bin = _find_spotdl(self.app_settings)
            if spotdl_bin is None:
                self.error.emit(
                    "spotdl executable not found. Place spotdl(.exe) in the program "
                    "folder or install it with: pip install spotdl"
                )
                self._flush_logs_now()
                self.finished.emit(-1)
                return

            cmd = self._build_command(spotdl_bin)
            env = self._build_process_env()

            title = self.item.get("title", self.item.get("url", "Unknown"))
            self.log.emit(f"\nStarting SpotDL download: {title}\n", AppStyles.SUCCESS_COLOR)
            self._flush_logs_now()

            self.process = QProcess(self)
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            if env is not None:
                self.process.setProcessEnvironment(env)
            self.process.readyReadStandardOutput.connect(self._on_read)
            self.process.errorOccurred.connect(self._on_qprocess_error)
            self.process.finished.connect(self._on_finished)

            self.process.start(str(cmd[0]), [str(a) for a in cmd[1:]])

            if not self.process.waitForStarted(5000):
                self.error.emit("Failed to start spotdl process.")
                self._flush_logs_now()
                self.finished.emit(-1)
        except Exception as e:
            self.error.emit(f"Error preparing SpotDL download: {e}")
            self._flush_logs_now()
            self.finished.emit(-1)

    # ------------------------------------------------------------------
    def cancel(self):
        self._cancel_requested = True
        if self.process and self.process.state() == QProcess.Running:
            self._add_log("⏹️ Cancelling SpotDL download...\n", AppStyles.WARNING_COLOR)
            self._flush_logs_now()
            try:
                self.process.terminate()
                if not self.process.waitForFinished(2000):
                    self.process.kill()
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    def _build_command(self, spotdl_bin: Path) -> List[str]:
        s = self.spotdl_settings
        a = self.app_settings
        url = self.item.get("url", "")

        cmd: List[str] = [str(spotdl_bin), "download", url]

        # Output directory: spotdl writes relative to CWD unless --output is absolute
        output_template = s.SPOTDL_OUTPUT or "{artists} - {title} - {year}.{output-ext}"
        # Combine downloads dir with template
        full_output = str(Path(a.DOWNLOADS_DIR) / output_template)
        cmd.extend(["--output", full_output])

        # Format
        cmd.extend(["--format", s.SPOTDL_FORMAT])

        # Threads
        cmd.extend(["--threads", str(max(1, s.SPOTDL_THREADS))])

        # Lyrics providers
        if s.SPOTDL_LYRICS:
            cmd += ["--lyrics"] + list(s.SPOTDL_LYRICS)

        # LRC sidecar files
        if s.SPOTDL_GENERATE_LRC:
            cmd.append("--generate-lrc")

        # Audio providers — only pass --audio when it differs from the
        # default fallback chain (youtube-music -> youtube). Adding more
        # providers beyond that increases per-track latency further.
        if s.SPOTDL_AUDIO_PROVIDERS and list(s.SPOTDL_AUDIO_PROVIDERS) != ["youtube-music", "youtube"]:
            cmd += ["--audio"] + list(s.SPOTDL_AUDIO_PROVIDERS)

        # Bitrate
        if s.SPOTDL_BITRATE and s.SPOTDL_BITRATE != "auto":
            cmd.extend(["--bitrate", s.SPOTDL_BITRATE])

        # Overwrite mode
        if s.SPOTDL_OVERWRITE:
            cmd.extend(["--overwrite", s.SPOTDL_OVERWRITE])

        # Playlist numbering
        if s.SPOTDL_PLAYLIST_NUMBERING:
            cmd.append("--playlist-numbering")

        # Skip explicit
        if s.SPOTDL_SKIP_EXPLICIT:
            cmd.append("--skip-explicit")

        # SponsorBlock
        if s.SPOTDL_SPONSOR_BLOCK:
            cmd.append("--sponsor-block")

        # Add unavailable tracks as empty files
        if s.SPOTDL_ADD_UNAVAILABLE:
            cmd.append("--add-unavailable")

        # ffmpeg location
        try:
            cmd.extend(["--ffmpeg", str(a.FFMPEG_PATH)])
        except Exception:
            pass

        # yt-dlp args passthrough
        if s.SPOTDL_YT_DLP_ARGS.strip():
            cmd.extend(["--yt-dlp-args", s.SPOTDL_YT_DLP_ARGS.strip()])

        # Extra ffmpeg args
        if s.SPOTDL_FFMPEG_ARGS.strip():
            cmd.extend(["--ffmpeg-args", s.SPOTDL_FFMPEG_ARGS.strip()])

        # Proxy: prefer override, else fall back to main proxy if enabled
        proxy = ""
        if not s.SPOTDL_USE_MAIN_PROXY:
            proxy = s.SPOTDL_PROXY.strip()
        else:
            proxy = (getattr(a, "PROXY_URL", "") or "").strip()
        if proxy:
            cmd.extend(["--proxy", proxy])

        # Cookie file (spotdl passes it to yt-dlp internally)
        try:
            if a.COOKIES_PATH.exists() and a.COOKIES_PATH.stat().st_size > 0:
                cmd.extend(["--cookie-file", str(a.COOKIES_PATH)])
        except Exception:
            pass

        # SSL
        if getattr(a, "IGNORE_SSL_ERRORS", False):
            # Pass through to yt-dlp via yt-dlp-args
            extra = "--no-check-certificates"
            idx = cmd.index("--yt-dlp-args") if "--yt-dlp-args" in cmd else -1
            if idx != -1:
                cmd[idx + 1] = cmd[idx + 1] + " " + extra
            else:
                cmd.extend(["--yt-dlp-args", extra])

        return [str(c) for c in cmd]

    # ------------------------------------------------------------------
    def _build_process_env(self) -> Optional[QProcessEnvironment]:
        try:
            env = QProcessEnvironment.systemEnvironment()
            extras: List[str] = []
            a = self.app_settings
            if getattr(a, "INTERNAL_DIR", None):
                extras.append(str(a.INTERNAL_DIR))
            if getattr(a, "BASE_DIR", None):
                extras.append(str(a.BASE_DIR))
            # deno needed by spotdl
            deno = getattr(a, "DENO_PATH", None)
            if deno and hasattr(deno, "exists"):
                try:
                    if deno.exists():
                        extras.append(str(deno.parent))
                except Exception:
                    pass
            if extras:
                cur = env.value("PATH", os.environ.get("PATH", ""))
                parts = cur.split(os.pathsep) if cur else []
                for p in reversed(extras):
                    if p and p not in parts:
                        parts.insert(0, p)
                env.insert("PATH", os.pathsep.join(parts))
            return env
        except Exception:
            return None

    # ------------------------------------------------------------------
    def _on_read(self):
        p = self.process
        if not p:
            return
        try:
            data = p.readAllStandardOutput().data()
            if not data:
                return
            text = data.decode(errors="ignore")

            is_error = "error" in text.lower() or "failed" in text.lower()
            color = AppStyles.ERROR_COLOR if is_error else AppStyles.TEXT_COLOR
            self._add_log(text, color)

            for m_err in self._track_error_re.finditer(text):
                snippet = m_err.group(0).strip()
                if snippet not in self._track_errors:
                    self._track_errors.append(snippet)

            # Extract progress: spotdl uses tqdm bars like "42%|████..."
            m = self._percent_re.search(text[-300:])
            if m:
                try:
                    pct = int(m.group(1))
                    eta_m = self._eta_re.search(text[-300:])
                    eta = f" ETA {eta_m.group(1)}" if eta_m else ""
                    status_text = f"{pct}%{eta}"
                    now = time.time()
                    if status_text != self._last_status_text and \
                            (now - self._last_status_emit) >= self._status_throttle_s:
                        self._last_status_text = status_text
                        self._last_status_emit = now
                        self.status.emit(status_text)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_qprocess_error(self, _code):
        self._add_log("❌ spotdl encountered a process error.\n", AppStyles.ERROR_COLOR)
        self._flush_logs_now()

    def _on_finished(self, exit_code: int, _status):
        try:
            if self._log_timer and self._log_timer.isActive():
                self._log_timer.stop()
        except Exception:
            pass

        self._flush_logs()

        if self._cancel_requested:
            self._add_log("⏹️ SpotDL download cancelled.\n", AppStyles.WARNING_COLOR)
            self._flush_logs_now()
            self.finished.emit(-1)
            return

        if exit_code == 0:
            if self._track_errors:
                self._add_log(
                    "⚠️ SpotDL finished, but "
                    f"{len(self._track_errors)} track(s) had errors:\n"
                    + "\n".join(f"   • {e}" for e in self._track_errors)
                    + "\n",
                    AppStyles.WARNING_COLOR,
                )
            else:
                self._add_log("✅ SpotDL download finished successfully.\n", AppStyles.SUCCESS_COLOR)
        else:
            self._add_log(f"❌ spotdl exited with code {exit_code}.\n", AppStyles.ERROR_COLOR)
        self._flush_logs_now()
        self.finished.emit(exit_code)

    # ------------------------------------------------------------------
    #  Log buffering
    # ------------------------------------------------------------------
    def _add_log(self, text: str, color: str):
        try:
            if len(self._log_buffer) > 1500:
                del self._log_buffer[:700]
            self._log_buffer.append((text, color))
        except Exception:
            pass

    def _flush_logs(self):
        if not self._log_buffer:
            return
        try:
            buf = self._log_buffer[:]
            self._log_buffer.clear()
        except Exception:
            buf = []

        cur_text_parts: List[str] = []
        cur_color: Optional[str] = None
        for text, color in buf:
            if cur_color is None:
                cur_color, cur_text_parts = color, [text]
            elif color == cur_color:
                cur_text_parts.append(text)
            else:
                try:
                    self.log.emit("\n".join(cur_text_parts), cur_color)
                except Exception:
                    pass
                cur_color, cur_text_parts = color, [text]
        if cur_color and cur_text_parts:
            try:
                self.log.emit("\n".join(cur_text_parts), cur_color)
            except Exception:
                pass

    def _flush_logs_now(self):
        try:
            self._flush_logs()
        except Exception:
            pass
