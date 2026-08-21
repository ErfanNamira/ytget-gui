# File: ytget_gui/workers/spotdl_worker.py
"""spotdl download worker.

Now built on BaseDownloadWorker and plain subprocess rather than QProcess.
QProcess.terminate() signals only the direct child, so cancelling a spotdl job
left the yt-dlp/ffmpeg processes it had spawned running in the background --
the download kept consuming bandwidth and writing files after the user stopped
it. proc.terminate_tree() takes the whole tree down.
"""

from __future__ import annotations

import codecs
import logging
import re
import subprocess
import threading
from pathlib import Path
from shutil import which
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Signal

from ytget_gui.settings import AppSettings
from ytget_gui.spotdl_settings import SpotDLSettings
from ytget_gui.styles import AppStyles
from ytget_gui.utils.paths import executable_name, is_usable_file
from ytget_gui.workers import fetch_core, proc, ssl_utils
from ytget_gui.workers.base import CANCELLED_EXIT, BaseDownloadWorker

log = logging.getLogger(__name__)


def _find_spotdl(settings: AppSettings) -> Optional[Path]:
    """Locate the spotdl binary: beside the app, in _internal, then on PATH."""
    name = executable_name("spotdl")
    for candidate in (settings.BASE_DIR / name, settings.INTERNAL_DIR / name):
        if candidate.is_file():
            return candidate
    found = which("spotdl")
    return Path(found) if found else None


# spotdl renders tqdm bars; the percentage is the only reliable field.
_PERCENT_RE = re.compile(r"(\d{1,3})%")
_ETA_RE = re.compile(r"(\d+:\d{2})\s*(?:remaining|left|eta)", re.IGNORECASE)

# spotdl exits 0 even when individual tracks in a batch fail, so a plain exit
# code is not enough to call the job successful.
_TRACK_ERROR_RE = re.compile(
    r"(AudioProviderError"
    r"|LookupError:[^\n]*not found"
    r"|Skipping [^\n]*\(as it is Explicit\)"
    r"|Could not match[^\n]*"
    r"|YT-DLP[^\n]*error)",
    re.IGNORECASE,
)


class SpotDLWorker(BaseDownloadWorker):
    _raw_output = Signal(bytes)
    _process_exited = Signal(int)

    def __init__(
        self,
        item: Dict[str, Any],
        settings: AppSettings,
        spotdl_settings: Optional[SpotDLSettings] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(item, **kwargs)
        self.settings = settings
        self.spotdl = spotdl_settings or settings.SPOTDL

        self._process: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._proc_lock = threading.Lock()
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._line_tail = ""
        self._track_errors: List[str] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _start(self) -> None:
        self._raw_output.connect(self._on_output)
        self._process_exited.connect(self._on_exit)

        binary = _find_spotdl(self.settings)
        if binary is None:
            self.error.emit(
                "spotdl not found. Place spotdl(.exe) next to the application "
                "or install it with: pip install spotdl"
            )
            self.emit_finished(CANCELLED_EXIT)
            return

        cmd = self._build_command(binary)
        env = proc.tool_env(self.settings)

        self.add_log(
            f"\nStarting SpotDL download: {self.title}", AppStyles.SUCCESS_COLOR
        )
        log.debug("spotdl command: %s", " ".join(cmd))
        self.flush_now()

        try:
            process = proc.spawn(cmd, env=env)
        except FileNotFoundError:
            self.error.emit(f"spotdl not found at {binary}")
            self.emit_finished(CANCELLED_EXIT)
            return
        except OSError as exc:
            self.error.emit(f"Failed to start spotdl: {exc}")
            self.emit_finished(CANCELLED_EXIT)
            return

        with self._proc_lock:
            self._process = process

        if self.cancelled:
            proc.terminate_tree(process)

        self._reader = threading.Thread(
            target=self._read_output, args=(process,), daemon=True,
            name="spotdl-reader",
        )
        self._reader.start()

    def _do_cancel(self) -> None:
        with self._proc_lock:
            process = self._process
        proc.terminate_tree(process)

    # ------------------------------------------------------------------
    # Command construction
    # ------------------------------------------------------------------

    def _build_command(self, binary: Path) -> List[str]:
        s = self.spotdl
        app = self.settings

        cmd: List[str] = [str(binary), "download", self.url]

        # spotdl resolves a relative --output against the process CWD, which for
        # a double-clicked build is arbitrary. Always hand it an absolute path.
        template = (s.SPOTDL_OUTPUT or "").strip() or "{artists} - {title} - {year}.{output-ext}"
        cmd += ["--output", str(Path(app.DOWNLOADS_DIR) / template)]

        cmd += ["--format", s.SPOTDL_FORMAT]
        cmd += ["--threads", str(max(1, min(32, int(s.SPOTDL_THREADS or 1))))]

        if s.SPOTDL_LYRICS:
            cmd += ["--lyrics", *s.SPOTDL_LYRICS]
        if s.SPOTDL_GENERATE_LRC:
            cmd.append("--generate-lrc")

        # Only pass --audio when it differs from spotdl's own preferred chain;
        # every extra provider adds per-track lookup latency.
        if s.SPOTDL_AUDIO_PROVIDERS and not s.uses_default_providers():
            cmd += ["--audio", *s.SPOTDL_AUDIO_PROVIDERS]

        if s.SPOTDL_BITRATE and s.SPOTDL_BITRATE != "auto":
            cmd += ["--bitrate", s.SPOTDL_BITRATE]
        if s.SPOTDL_OVERWRITE:
            cmd += ["--overwrite", s.SPOTDL_OVERWRITE]

        if s.SPOTDL_PLAYLIST_NUMBERING:
            cmd.append("--playlist-numbering")
        if s.SPOTDL_SKIP_EXPLICIT:
            cmd.append("--skip-explicit")
        if s.SPOTDL_SPONSOR_BLOCK:
            cmd.append("--sponsor-block")
        if s.SPOTDL_ADD_UNAVAILABLE:
            cmd.append("--add-unavailable")

        ffmpeg = Path(app.FFMPEG_PATH)
        if ffmpeg.is_file():
            cmd += ["--ffmpeg", str(ffmpeg)]

        # Assemble the yt-dlp passthrough once. The previous revision appended
        # --yt-dlp-args, then later located that flag by index and string-
        # concatenated onto its value to bolt on --no-check-certificates; if the
        # flag was absent it appended a second --yt-dlp-args, and spotdl keeps
        # only the last one, so the user's own args were silently discarded.
        yt_args: List[str] = []
        user_args = (s.SPOTDL_YT_DLP_ARGS or "").strip()
        if user_args:
            yt_args.append(user_args)
        _verify, ssl_args, _env = ssl_utils.resolve_ssl_config(app)
        if ssl_args:
            yt_args.append(" ".join(ssl_args))
        if yt_args:
            cmd += ["--yt-dlp-args", " ".join(yt_args)]

        ffmpeg_args = (s.SPOTDL_FFMPEG_ARGS or "").strip()
        if ffmpeg_args:
            cmd += ["--ffmpeg-args", ffmpeg_args]

        proxy = (
            (getattr(app, "PROXY_URL", "") or "").strip()
            if s.SPOTDL_USE_MAIN_PROXY
            else (s.SPOTDL_PROXY or "").strip()
        )
        if proxy:
            cmd += ["--proxy", proxy]

        if is_usable_file(app.COOKIES_PATH):
            cmd += ["--cookie-file", str(app.COOKIES_PATH)]

        return [str(part) for part in cmd]

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _read_output(self, process: subprocess.Popen) -> None:
        stream = process.stdout
        if stream is None:
            self._process_exited.emit(CANCELLED_EXIT)
            return
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                self._raw_output.emit(chunk)
        except (OSError, ValueError):
            pass
        finally:
            try:
                code = process.wait()
            except OSError:
                code = CANCELLED_EXIT
            self._process_exited.emit(code if code is not None else CANCELLED_EXIT)

    def _on_output(self, data: bytes) -> None:
        text = self._decoder.decode(data)
        if not text:
            return

        for match in _TRACK_ERROR_RE.finditer(text):
            snippet = match.group(0).strip()
            if snippet not in self._track_errors:
                self._track_errors.append(snippet)

        self._update_progress(text)

        # tqdm redraws its bar with carriage returns. Treating \r as a line
        # break keeps thousands of redraw frames out of the console.
        buffer = self._line_tail + text
        segments = re.split(r"[\r\n]", buffer)
        self._line_tail = "" if buffer.endswith(("\r", "\n")) else segments.pop()

        for segment in segments:
            stripped = segment.strip()
            if not stripped or _PERCENT_RE.search(stripped):
                continue
            lowered = stripped.lower()
            if "error" in lowered or "failed" in lowered:
                colour = AppStyles.ERROR_COLOR
            elif "warning" in lowered or "skipping" in lowered:
                colour = AppStyles.WARNING_COLOR
            else:
                colour = AppStyles.TEXT_COLOR
            self.add_log(stripped, colour)

    def _update_progress(self, text: str) -> None:
        tail = text[-400:]
        match = None
        for match in _PERCENT_RE.finditer(tail):
            pass  # keep the most recent percentage in the chunk
        if match is None:
            return
        try:
            percent = int(match.group(1))
        except ValueError:
            return
        self.emit_progress(percent)
        eta = _ETA_RE.search(tail)
        self.emit_stage(f"{percent}%" + (f" \u00b7 ETA {eta.group(1)}" if eta else ""))

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    def _on_exit(self, code: int) -> None:
        with self._proc_lock:
            self._process = None

        if self._line_tail.strip() and not _PERCENT_RE.search(self._line_tail):
            self.add_log(self._line_tail.strip(), AppStyles.TEXT_COLOR)
        self._line_tail = ""
        self.flush()

        if self.cancelled:
            self.add_log("\u23f9\ufe0f SpotDL download cancelled.", AppStyles.WARNING_COLOR)
            self.emit_finished(CANCELLED_EXIT)
            return

        if code != 0:
            self.add_log(f"\u274c spotdl exited with code {code}.", AppStyles.ERROR_COLOR)
            self.emit_finished(code)
            return

        if self._track_errors:
            preview = self._track_errors[:10]
            body = "\n".join(f"   \u2022 {e}" for e in preview)
            if len(self._track_errors) > len(preview):
                body += f"\n   \u2022 \u2026and {len(self._track_errors) - len(preview)} more"
            self.add_log(
                f"\u26a0\ufe0f SpotDL finished, but {len(self._track_errors)} track(s) "
                f"had errors:\n{body}",
                AppStyles.WARNING_COLOR,
            )
        else:
            self.add_log(
                "\u2705 SpotDL download finished successfully.", AppStyles.SUCCESS_COLOR
            )

        self.emit_progress(100)
        self.emit_finished(0)
