# File: ytget_gui/workers/download_worker.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer
import codecs
import os
import re
import shutil
import signal
import sys
import time
import subprocess
import threading

from ytget_gui.styles import AppStyles
from ytget_gui.settings import AppSettings, FILENAME_FORMAT_PRESETS
from ytget_gui.workers import cookies as CookieManager
from ytget_gui.workers import ssl_utils

@dataclass
class QueueItem:
    url: str
    title: str
    format_code: str


class DownloadWorker(QObject):
    log = Signal(str, str)
    finished = Signal(int)
    error = Signal(str)
    status = Signal(str)

    _rawOutput = Signal(bytes)
    _procFinished = Signal(int)

    def __init__(
        self,
        item: Dict[str, Any],
        settings: AppSettings,
        log_flush_ms: int = 300,
        status_throttle_ms: int = 500,
    ):
        super().__init__()
        self.item = item
        self.settings = settings
        self.process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._cancel_requested = False
        self._flat_playlist_dir: Optional[Path] = None

        # Log buffer and timer (timer created in run so it lives in worker thread)
        self._log_buffer: List[Tuple[str, str]] = []
        self._log_timer: Optional[QTimer] = None
        self._log_flush_ms = max(100, int(log_flush_ms))

        # Regexes and tokens
        self._percent_re = re.compile(r"([0-9]{1,3}(?:[.,][0-9]+)?)\s*%")
        self._download_tag = "[download]"
        self._error_sub = "error"

        # yt-dlp's stdout is read in fixed-size raw byte chunks (see
        # _read_process_output). A multi-byte UTF-8 character (accented
        # letters, CJK titles, emoji, etc) can land right on a chunk
        # boundary; decoding each chunk independently with
        # bytes.decode(errors="ignore") silently drops/replaces those
        # bytes because the trailing partial sequence looks invalid on
        # its own. An incremental decoder keeps the undecoded tail bytes
        # around and completes them once the rest arrives, so titles and
        # log text no longer get corrupted mid-word.
        self._utf8_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        # status throttle
        self._last_status_text: Optional[str] = None
        self._last_status_emit = 0.0
        self._status_throttle_s = max(0.05, status_throttle_ms / 1000.0)

        # flush emit caps
        self._max_emit_bytes = 100 * 1024  # max bytes emitted per flush to avoid UI flood
        self._max_entries_per_flush = 200   # safety cap on number of signals emitted per flush

        # --- Auto-retry state ---
        # yt-dlp exits non-zero for a wide range of reasons, some of which are
        # purely transient (expired signed URL -> 403, a format that is
        # momentarily unavailable, dropped connections, rate limiting, etc).
        # A fresh yt-dlp invocation gets a fresh signed URL, which is why
        # simply re-running the same command after a short pause usually
        # just works. Previously any non-zero exit was treated as final, so
        # a mid-download 403 permanently failed the item even though
        # --retries only covers within-process HTTP retries, not "the whole
        # video URL expired" cases. We now detect known-transient failures
        # and silently re-run the same command a few times, with backoff,
        # before giving up for real.
        self._cmd: List[str] = []
        self._env: Optional[Dict[str, str]] = None
        self._recent_output: str = ""
        self._internal_attempt: int = 0
        self._max_internal_retries: int = max(0, int(getattr(self.settings, "AUTO_RETRY_COUNT", 3) or 0))
        self._retry_backoff_base_s: float = 3.0

    # A handful of failures are permanent no matter how many times we retry --
    # retrying these just wastes time and delays the user finding out.
    _FATAL_RE = re.compile(
        r"(Video unavailable|This video is (?:private|unavailable)|"
        r"has been removed by the uploader|"
        r"account associated with this video has been terminated|"
        r"Sign in to confirm your age|"
        r"copyright (?:grounds|claim)|"
        r"is not available in your country|"
        r"This live event will begin in|"
        r"members-only content)",
        re.IGNORECASE,
    )

    # Known-transient failures worth silently re-running the whole command for.
    _RETRYABLE_RE = re.compile(
        r"(HTTP Error 403|HTTP Error 429|HTTP Error 5\d\d|"
        r"Requested format is not available|"
        r"Connection reset|Connection aborted|Remote end closed connection|"
        r"Read timed out|The read operation timed out|"
        r"Temporary failure in name resolution|Name or service not known|"
        r"unable to download video data|"
        r"unable to download webpage|"
        r"Got error|urlopen error|"
        r"Broken pipe|EOF occurred in violation of protocol)",
        re.IGNORECASE,
    )

    # run should be invoked in a worker thread via moveToThread
    def run(self):
        try:
            # create timer with self as parent so it lives in this object's thread
            if self._log_timer is None:
                self._log_timer = QTimer(self)
                self._log_timer.setInterval(self._log_flush_ms)
                self._log_timer.timeout.connect(self._flush_logs)
                self._log_timer.start()

            # Connect once: these route data from the background reader
            # thread back onto this worker's own thread safely.
            self._rawOutput.connect(self._on_read_bytes)
            self._procFinished.connect(self._on_finished_signal)

            # Try to refresh cookies if user enabled auto-refresh
            try:                       
                if getattr(self.settings, "COOKIES_AUTO_REFRESH", False) and getattr(self.settings, "COOKIES_FROM_BROWSER", ""):
                    ok, msg = CookieManager.refresh_before_download(self.settings)
                    if ok:
                        # Inform UI
                        self._add_log(f"🔐 Refreshed cookies: {msg}\n", AppStyles.INFO_COLOR)

                        # Make settings reflect export: set COOKIES_PATH to exported file if present,
                        # set COOKIES_LAST_IMPORTED to UTC timestamp, and persist config.
                        try:
                            # If refresh_before_download wrote to settings.COOKIES_PATH or BASE_DIR/cookies.txt,
                            # ensure settings.COOKIES_PATH is a Path instance pointing at the file.
                            exported_path = getattr(self.settings, "COOKIES_PATH", None)
                            if not exported_path or str(exported_path) == "":
                                exported_path = Path(getattr(self.settings, "BASE_DIR", Path("."))) / "cookies.txt"
                            self.settings.COOKIES_PATH = Path(exported_path)

                            from datetime import datetime
                            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                            self.settings.COOKIES_LAST_IMPORTED = ts

                            if hasattr(self.settings, "save_config"):
                                self.settings.save_config()
                        except Exception:
                            # best-effort only
                            pass
                    else:
                        self._add_log(f"⚠️ Cookies refresh: {msg}\n", AppStyles.WARNING_COLOR)                      
            except Exception:
                pass

            cmd = self._build_command()
            env = self._build_process_env(cmd)
            self._cmd = cmd
            self._env = env

            # startup log and immediate flush so GUI sees it fast
            self.log.emit(f"\nStarting Download for: {(self.item.get('title', 'Unknown'))}", AppStyles.SUCCESS_COLOR)
            self._flush_logs_now()

            if not self._spawn_process(cmd, env):
                return

            # Read process output on a background thread and forward it into
            # the existing buffered-logging pipeline.
            self._reader_thread = threading.Thread(
                target=self._read_process_output, daemon=True
            )
            self._reader_thread.start()
        except Exception as e:
            self.error.emit(f"Error preparing download: {e}")
            self._flush_logs_now()
            self.finished.emit(-1)

    def _spawn_process(self, cmd: List[str], env: Optional[Dict[str, str]]) -> bool:
        """Launch (or re-launch, on retry) the yt-dlp subprocess. Returns
        True on success; on failure it emits error/finished itself and
        returns False."""
        program = cmd[0]
        args = cmd[1:]

        # On Windows, prevent a console window from flashing when the
        # child process (yt-dlp / ffmpeg) starts. QProcess's
        # setCreateProcessArgumentsModifier isn't wrapped by PySide6, so
        # we use subprocess.Popen directly, which does support this.
        creationflags = 0
        startupinfo = None
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            popen_kwargs: Dict[str, Any] = {}
            if sys.platform != "win32":
                # yt-dlp spawns ffmpeg/aria2c as *its own* child processes.
                # Without this, terminate()/kill() below only signals the
                # yt-dlp process itself and leaves those children running
                # as orphans -- which is why cancelling a download (e.g.
                # via "Remove" on the active item) didn't actually stop
                # disk/network activity. start_new_session puts yt-dlp
                # (and everything it spawns) in its own process group so
                # the whole tree can be killed together in cancel().
                popen_kwargs["start_new_session"] = True
            self.process = subprocess.Popen(
                [program, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=creationflags,
                startupinfo=startupinfo,
                bufsize=0,  # unbuffered: deliver bytes as soon as they arrive
                **popen_kwargs,
            )
            return True
        except Exception as e:
            self.error.emit(f"Failed to start yt-dlp process: {e}")
            self._flush_logs_now()
            self.finished.emit(-1)
            return False

    def _retry_launch(self):
        """Re-run the same yt-dlp command after a transient failure."""
        if self._cancel_requested:
            self.finished.emit(-1)
            return
        self._recent_output = ""
        if not self._spawn_process(self._cmd, self._env):
            return
        self._reader_thread = threading.Thread(
            target=self._read_process_output, daemon=True
        )
        self._reader_thread.start()

    # Runs on a background thread: reads the child process's merged
    # stdout/stderr stream and hands chunks off to the existing handlers.
    def _read_process_output(self):
        p = self.process
        if p is None or p.stdout is None:
            self._procFinished.emit(-1)
            return
        try:
            # 64KB reads instead of 4KB: fewer, larger cross-thread signal
            # emissions for the same amount of output. Each _rawOutput.emit()
            # crosses from this reader thread onto the worker's own thread
            # via a queued Qt event; under verbose/high-throughput output
            # (large playlists, -v) the old 4KB size meant a lot more queued
            # events than necessary, which is a real source of GUI stutter
            # even though the log buffer downstream is already batched.
            while True:
                chunk = p.stdout.read(65536)
                if not chunk:
                    break
                self._rawOutput.emit(chunk)
        except Exception:
            pass
        finally:
            try:
                exit_code = p.wait()
            except Exception:
                exit_code = -1
            self._procFinished.emit(exit_code)

    def _on_finished_signal(self, exit_code: int):
        # Thin wrapper so the two-arg _on_finished (kept for readability/
        # symmetry with the old QProcess.finished signature) can be
        # connected to the single-arg _procFinished signal.
        self._on_finished(exit_code, None)

    def cancel(self):
        self._cancel_requested = True
        p = self.process
        if p and p.poll() is None:
            self._add_log("⏹️ Cancelling Download...\n", AppStyles.WARNING_COLOR)
            self._flush_logs_now()
            try:
                if sys.platform == "win32":
                    # p.terminate() (== TerminateProcess) only kills yt-dlp
                    # itself, not the ffmpeg/aria2c children it launched --
                    # those kept running in the background, which is why
                    # "removing" an in-progress item didn't actually stop
                    # the download. taskkill /T kills the whole process tree.
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(p.pid)],
                        capture_output=True,
                    )
                else:
                    # start_new_session=True at launch put yt-dlp in its own
                    # process group, so signalling the group (not just the
                    # single pid) takes its ffmpeg/aria2c children down too.
                    pgid = os.getpgid(p.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    try:
                        p.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(pgid, signal.SIGKILL)
            except Exception:
                try:
                    p.terminate()
                    try:
                        p.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        p.kill()
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass

    # Build a minimal environment for child process, adding PhantomJS only when explicitly requested
    def _build_process_env(self, cmd: List[str]) -> Optional[Dict[str, str]]:
        try:
            env = os.environ.copy()
            extras: List[str] = []
            if getattr(self.settings, "INTERNAL_DIR", None):
                extras.append(str(self.settings.INTERNAL_DIR))
            if getattr(self.settings, "BASE_DIR", None):
                extras.append(str(self.settings.BASE_DIR))

            # Only add phantomjs parent dir if settings explicitly want it (new flag USE_PHANTOMJS)
            ph = getattr(self.settings, "PHANTOMJS_PATH", None)
            use_phantom = getattr(self.settings, "USE_PHANTOMJS", False)
            if use_phantom and ph and hasattr(ph, "exists"):
                try:
                    if ph.exists():
                        extras.append(str(ph.parent))
                except Exception:
                    pass
                    
            # Add deno parent dir if deno binary is present
            deno = getattr(self.settings, "DENO_PATH", None)
            if deno and hasattr(deno, "exists"):
                try:
                    if deno.exists():
                        extras.append(str(deno.parent))
                except Exception:
                    pass

            if extras:
                cur = env.get("PATH", "")
                parts = cur.split(os.pathsep) if cur else []
                # insert extras at front in stable order
                for p in reversed(extras):
                    if p and p not in parts:
                        parts.insert(0, p)
                env["PATH"] = os.pathsep.join(parts)

            ssl_env = getattr(self, "_ssl_env", None)
            if ssl_env:
                env.update(ssl_env)

            return env
        except Exception:
            return None

    # lightweight read handler that extracts and throttles progress info
    # (called from the background reader thread with a raw bytes chunk)
    def _on_read_bytes(self, data: bytes):
        if not data:
            return
        try:
            text = self._utf8_decoder.decode(data)
            if not text:
                # Only got part of a multi-byte character; the decoder is
                # holding the partial bytes and will emit them once the
                # rest arrives in a later chunk.
                return

            # quick error detection
            is_error = self._error_sub in text.lower()
            color = AppStyles.ERROR_COLOR if is_error else AppStyles.TEXT_COLOR

            # Append raw chunk to buffer (batching avoids signaling per chunk)
            self._add_log(text, color)

            # Keep a small rolling window of raw output so _on_finished can
            # sniff it for known-transient error patterns (403, format not
            # available, dropped connections, etc) to decide whether to
            # silently retry the whole download.
            self._recent_output = (self._recent_output + text)[-8000:]

            # attempt progress extraction if possible, keep it cheap
            tail = text[-300:]  # small window where progress typically lives
            if (self._download_tag in tail) or ("%" in tail):
                m = self._percent_re.search(tail)
                pct_text: Optional[str] = None
                if m:
                    try:
                        pct_val = int(float(m.group(1).replace(",", ".")))
                        pct_text = f"{pct_val}%"
                    except Exception:
                        pct_text = m.group(1) + "%"

                eta_text: Optional[str] = None
                up = tail.upper()
                pos = up.rfind("ETA")
                if pos != -1:
                    after = tail[pos + 3 :].strip()
                    token = after.split()[0] if after.split() else ""
                    if ":" in token or token.isdigit():
                        eta_text = token

                if pct_text:
                    status_text = pct_text + (f" ETA {eta_text}" if eta_text else "")
                    now = time.time()
                    if status_text != self._last_status_text and (now - self._last_status_emit) >= self._status_throttle_s:
                        self._last_status_text = status_text
                        self._last_status_emit = now
                        try:
                            self.status.emit(status_text)
                        except Exception:
                            pass

            # If buffer is huge, trigger immediate flush but still keep it batched
            if len(self._log_buffer) > 800:
                self._flush_logs()
        except Exception:
            # swallow exceptions to keep worker alive
            pass

    def _on_finished(self, exit_code: int, _status):
        try:
            if self._log_timer and self._log_timer.isActive():
                self._log_timer.stop()
        except Exception:
            pass

        try:
            # final flush
            self._flush_logs()
        except Exception:
            pass

        if self._cancel_requested:
            self._add_log("⏹️ Download cancelled by user.\n", AppStyles.WARNING_COLOR)
            self._flush_logs_now()
            self.finished.emit(-1)
            return

        if exit_code == 0:
            self._add_log("✅ Download Finished Successfully.\n", AppStyles.SUCCESS_COLOR)
            self._flush_logs_now()
            try:
                if getattr(self, "_flat_playlist_dir", None):
                    tagged = self._tag_flat_playlist_tracks()
                    if tagged > 0:
                        self._add_log(f"🔢 Tagged track numbers for {tagged} file(s).\n", AppStyles.SUCCESS_COLOR)
                        self._flush_logs_now()
            except Exception:
                pass
            try:
                if self._is_audio_download():
                    cleaned = self._clean_music_video_tags()
                    if cleaned > 0:
                        self._add_log(f"✨ Cleaned {cleaned} filename(s).\n", AppStyles.SUCCESS_COLOR)
                        self._flush_logs_now()
            except Exception:
                pass
            self.finished.emit(0)
            return

        # --- Non-zero exit: decide whether to silently retry ---
        if self._should_auto_retry():
            self._internal_attempt += 1
            delay_s = min(30.0, self._retry_backoff_base_s * self._internal_attempt)
            self._add_log(
                f"⚠️ Recoverable error (exit {exit_code}); the request likely expired. "
                f"Retrying in {delay_s:.0f}s… (attempt {self._internal_attempt}/{self._max_internal_retries})\n",
                AppStyles.WARNING_COLOR,
            )
            self._flush_logs_now()
            try:
                if self._log_timer and not self._log_timer.isActive():
                    self._log_timer.start()
            except Exception:
                pass
            QTimer.singleShot(int(delay_s * 1000), self._retry_launch)
            return

        self._add_log(f"❌ yt-dlp exited with code {exit_code}.\n", AppStyles.ERROR_COLOR)
        self._flush_logs_now()
        self.finished.emit(exit_code)

    def _should_auto_retry(self) -> bool:
        if self._cancel_requested:
            return False
        if self._internal_attempt >= self._max_internal_retries:
            return False
        text = self._recent_output
        if not text:
            return False
        if self._FATAL_RE.search(text):
            return False
        return bool(self._RETRYABLE_RE.search(text))

    # --- Helpers ---
    def _short(self, title: str) -> str:
        title = title or ""
        return title[:50] + "..." if len(title) > 50 else title

    @staticmethod
    def is_short_video(url: str) -> bool:
        return "youtube.com/shorts/" in (url or "")

    @staticmethod
    def is_youtube_music_url(url: str) -> bool:
        """
        Return True only for actual YouTube Music URLs (music.youtube.com),
        not regular youtube.com/youtu.be URLs.
        """
        u = (url or "").lower()
        return "music.youtube.com" in u

    # YouTube (all variants) always exposes its full-resolution ladder via
    # regular DASH (MPD) manifests, and the extra Referer/User-Agent headers
    # this HLS-preference path adds are neither needed nor helpful there.
    # Forcing HLS on YouTube caps quality at whatever muxed HLS format it
    # happens to publish for that video (frequently only 1080p60, even when
    # 1440p/4K exist as separate DASH video-only streams) -- so YouTube is
    # excluded here unconditionally, regardless of what a user may have
    # (likely accidentally) added to HLS_PREFERRED_DOMAINS. This setting
    # exists for sites that genuinely only serve usable streams over HLS.
    _HLS_EXCLUDED_DOMAINS = ("youtube.com", "youtu.be")

    def _is_hls_preferred_site(self, url: str) -> bool:
        """
        Return True when HLS should be preferred for this URL.
        Controlled by settings.PREFER_HLS and settings.HLS_PREFERRED_DOMAINS.
        """
        try:
            if not getattr(self.settings, "PREFER_HLS", False):
                return False
            u = (url or "").lower()
            if any(d in u for d in self._HLS_EXCLUDED_DOMAINS):
                return False
            domains = getattr(self.settings, "HLS_PREFERRED_DOMAINS", []) or []
            return any(d in u for d in domains)
        except Exception:
            return False

    def _detect_flat_playlist(self, url: str) -> bool:
        """
        Peek at the playlist title the same way ytgetmusic.sh does, to detect
        YouTube Music's auto-generated "Top songs" / "Mix" / "Radio" playlists,
        which have no real per-track album and need special handling.
        """
        if not url:
            return False
        try:
            result = subprocess.run(
                [
                    str(self.settings.YT_DLP_PATH),
                    "--flat-playlist",
                    "--playlist-items", "1",
                    "--print", "%(playlist_title)s",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return False
            title = (result.stdout or "").strip()
            return title in ("Top songs", "Mix", "Radio")
        except Exception:
            return False

    def _tag_flat_playlist_tracks(self) -> int:
        """
        eyeD3-based track-number fix for flat playlists, matching ytgetmusic.sh.
        yt-dlp's --parse-metadata can't reliably derive %(track_number)s from
        %(autonumber)s at postprocessing time in this mode, so we tag the files
        directly from their "NNN - ..." filenames after the download finishes.
        """
        d = getattr(self, "_flat_playlist_dir", None)
        if not d or not Path(d).exists():
            return 0
        if not shutil.which("eyeD3"):
            self._add_log("⚠️ eyeD3 not found; skipping track-number tagging.\n", AppStyles.WARNING_COLOR)
            return 0

        tagged = 0
        for f in sorted(Path(d).glob("*.mp3")):
            base = f.name
            track_token = base.split(" ", 1)[0]
            if not track_token.isdigit():
                continue
            try:
                track = int(track_token)
                subprocess.run(
                    ["eyeD3", "--track", str(track), str(f)],
                    capture_output=True,
                    timeout=30,
                )
                tagged += 1
            except Exception:
                pass
        return tagged

    def _is_audio_download(self, code: Optional[str] = None) -> bool:
        """
        Return True if the provided format code (or the item's format_code if None)
        corresponds to an audio-only selection.
        """
        try:
            code = code if code is not None else self.item.get("format_code", "")
            return str(code) in ("bestaudio", "playlist_mp3", "audio_flac", "audio_opus", "playlist_opus")
        except Exception:
            return False

    def _should_force_title(self, is_playlist: bool) -> bool:
        s = self.settings
        try:
            no_cookie = not (s.COOKIES_PATH.exists() and s.COOKIES_PATH.stat().st_size > 0)
            no_browser = not bool(getattr(s, "COOKIES_FROM_BROWSER", None))
            return (not is_playlist) and no_cookie and no_browser
        except Exception:
            return (not is_playlist)

    def _resolve_name_template(self, default_template: str) -> str:
        """
        Returns the yt-dlp filename template "stub" (title portion, no extension)
        according to the user's FILENAME_FORMAT preference. Falls back to
        default_template (legacy behavior) when the preference is "default",
        an unrecognized value, or "custom" without a template provided.
        """
        s = self.settings
        fmt = getattr(s, "FILENAME_FORMAT", "default") or "default"
        if fmt == "default":
            return default_template
        if fmt == "custom":
            custom = (getattr(s, "CUSTOM_FILENAME_TEMPLATE", "") or "").strip()
            return custom if custom else default_template
        return FILENAME_FORMAT_PRESETS.get(fmt, default_template)

    def _safe_filename(self, name: str) -> str:
        if not name:
            return "Unknown"
        name = "".join(ch for ch in name if ord(ch) >= 32)
        name = re.sub(r'[\\/:*?"<>|]', " ", name)
        name = re.sub(r"\s+", " ", name).strip().rstrip(" .")
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        if name.upper() in reserved:
            name += "_"
        if len(name) > 180:
            name = name[:180].rstrip(" .")
        return name or "Unknown"

    def _build_command(self) -> List[str]:
        s = self.settings
        it = self.item

        cmd: List[str] = [
            str(s.YT_DLP_PATH),
            "--no-warnings",
            "--no-overwrites",
            "--progress",
            "--newline",
            "--output-na-placeholder", "Unknown",
            "--ffmpeg-location", str(s.FFMPEG_PATH.parent),
        ]

        format_code = it.get("format_code", "")
        # Normalize format_code so it is a valid yt-dlp format selector string.
        # Accepts three common inputs from the UI:
        # 1) preset label keys from AppSettings.RESOLUTIONS (map to their value)
        # 2) numeric height tokens like "1080p" (convert to format chain)
        # 3) already-valid format strings
        try:
            if isinstance(format_code, str) and format_code in getattr(s, "RESOLUTIONS", {}):
                # User selected a preset label from the UI; map to the actual selector
                format_code = s.RESOLUTIONS.get(format_code, format_code)
            else:
                # If user provided a simple height token like "1080p", convert it
                m = re.match(r"^(\d+)p$", str(format_code).strip())
                if m:
                    try:
                        height = int(m.group(1))
                        format_code = s.get_format_for_resolution(height)
                    except Exception:
                        # leave format_code unchanged on error
                        pass
        except Exception:
            # keep original format_code if anything goes wrong
            pass        

        # Determine playlist/audio flags from the normalized format_code and URL
        is_playlist = "list=" in (it.get("url", "") or "") or format_code in ("playlist_mp3", "playlist_opus")
        # Use the normalized format_code when deciding audio vs video
        is_audio = self._is_audio_download(format_code)
        is_flac = (isinstance(format_code, str) and format_code == "audio_flac")
        is_opus = (isinstance(format_code, str) and format_code in ("audio_opus", "playlist_opus"))

        # Reset any state left over from a previous run of this worker
        self._flat_playlist_dir: Optional[Path] = None

        # YouTube Music's auto-generated "Top songs" / "Mix" / "Radio" playlists have no
        # real album for each track, so yt-dlp can't recover per-track artist/album via
        # its normal metadata extraction. We detect this case the same way the working
        # ytgetmusic.sh script does (peek at the playlist title) and handle it specially
        # below instead of guessing at metadata via regex.
        is_flat_playlist = False
        if (
            is_audio
            and is_playlist
            and getattr(s, "YT_MUSIC_METADATA", False)
            and self.is_youtube_music_url(it.get("url", "") or "")
        ):
            is_flat_playlist = self._detect_flat_playlist(it.get("url", "") or "")

        if s.COOKIES_PATH.exists() and s.COOKIES_PATH.stat().st_size > 0:
            cmd.extend(["--cookies", str(s.COOKIES_PATH)])
        if getattr(s, "COOKIES_FROM_BROWSER", None):
            cmd.extend(["--cookies-from-browser", s.COOKIES_FROM_BROWSER])
        if getattr(s, "PROXY_URL", ""):
            cmd.extend(["--proxy", s.PROXY_URL])
        if getattr(s, "LIMIT_RATE", ""):
            cmd.extend(["--limit-rate", s.LIMIT_RATE])
        retries = str(getattr(s, "RETRIES", 10))
        cmd.extend(["--retries", retries])
        # yt-dlp only auto-retries --retries times for the *same* signed URL;
        # spacing those attempts out (instead of hammering immediately) gives
        # transient 403/429/5xx responses a real chance to clear, and
        # explicitly matching --fragment-retries avoids it silently falling
        # back to a different default for HLS/DASH fragment downloads.
        cmd.extend(["--fragment-retries", retries])
        cmd.extend(["--extractor-retries", str(getattr(s, "RETRIES", 10))])
        cmd.extend(["--retry-sleep", "linear=1::2"])
        cmd.extend(["--file-access-retries", "3"])

        if getattr(s, "DATEAFTER", ""):
            cmd.extend(["--dateafter", s.DATEAFTER])
        if getattr(s, "LIVE_FROM_START", False):
            cmd.append("--live-from-start")
        if is_playlist:
            cmd.append("--ignore-errors")
        if getattr(s, "ENABLE_ARCHIVE", False):
            cmd.extend(["--download-archive", str(s.ARCHIVE_PATH)])
        if getattr(s, "PLAYLIST_REVERSE", False):
            cmd.append("--playlist-reverse")
        if getattr(s, "PLAYLIST_ITEMS", ""):
            cmd.extend(["--playlist-items", s.PLAYLIST_ITEMS])
        if getattr(s, "CLIP_START", None) and getattr(s, "CLIP_END", None):
            cmd.extend(["--download-sections", f"*{s.CLIP_START}-{s.CLIP_END}"])

        flat_album_name: Optional[str] = None

        if is_flat_playlist:
            # Mirrors ytgetmusic.sh's SAFE_NAME/-o template for "Top songs"/Mix/Radio:
            # everything goes in one folder, numbered by download order, with an
            # explicit album tag (set below) instead of a guessed one.
            flat_album_name = self._safe_filename(it.get("title") or "Playlist") + " Playlist"
            base = Path(s.DOWNLOADS_DIR) / flat_album_name
            name_tmpl = self._resolve_name_template("%(album)s - %(title)s")
            filename = f"%(autonumber)03d - {name_tmpl}.%(ext)s"
            self._flat_playlist_dir = base
        else:
            if is_playlist:
                base = Path(s.DOWNLOADS_DIR) / "%(playlist_title)s"
                if getattr(s, "ORGANIZE_BY_UPLOADER", False):
                    base /= "%(uploader)s"
            else:
                base = Path(s.DOWNLOADS_DIR)
                if getattr(s, "ORGANIZE_BY_UPLOADER", False):
                    base /= "%(uploader)s"

            is_yt_music = self.is_youtube_music_url(it.get("url", "") or "")
            if getattr(s, "YT_MUSIC_METADATA", False) and is_yt_music and (is_audio or is_playlist):
                default_stub = "%(artist)s - %(title)s"
            else:
                default_stub = "%(title)s"
            name_tmpl = self._resolve_name_template(default_stub)
            fallback = f"{name_tmpl}.%(ext)s"

            if self._should_force_title(is_playlist) and getattr(s, "FILENAME_FORMAT", "default") == "default":
                safe = self._safe_filename(it.get("title") or "Unknown")
                filename = f"{safe}.%(ext)s"
            else:
                filename = fallback

        out_tmpl = str(Path(base) / filename)
        if is_playlist:
            cmd.extend(["--yes-playlist", "-o", out_tmpl])
        else:
            cmd.extend(["-o", out_tmpl])

        if is_audio:
            if is_flac:
                audio_format = "flac"
            elif is_opus:
                audio_format = "opus"
            else:
                audio_format = "mp3"

            cmd.extend([
                "-f", "bestaudio",
                "--extract-audio",
                "--audio-format", audio_format,
                "--embed-thumbnail",
            ])
            if getattr(s, "ADD_METADATA", False):
                cmd.append("--add-metadata")
            if not is_flac:
                cmd.extend(["--audio-quality", "0"])

            # NOTE: yt-dlp does not merge multiple `--postprocessor-args ffmpeg:...`
            # flags -- a later one can overwrite an earlier one for the same
            # postprocessor. So any ffmpeg: args below must be combined into a
            # single call rather than issued separately.
            ffmpeg_pp_args: List[str] = []
            if is_flac:
                ffmpeg_pp_args.extend(["-compression_level", "12", "-sample_fmt", "s16"])
            if is_playlist and getattr(s, "YT_MUSIC_METADATA", False) and is_yt_music and is_flat_playlist:
                # No real per-track album exists for these playlists, so set one
                # explicitly (like SAFE_NAME in ytgetmusic.sh) instead of letting
                # yt-dlp guess. Artist/title are left untouched -- yt-dlp's own
                # metadata extraction from YouTube Music is accurate; the old
                # description-regex hack here is what was blanking/corrupting them.
                ffmpeg_pp_args.extend(["-metadata", f'album="{flat_album_name}"'])
            if ffmpeg_pp_args:
                cmd.extend(["--postprocessor-args", "ffmpeg:" + " ".join(ffmpeg_pp_args)])

            # %(track_number)s is not populated by yt-dlp on its own for regular
            # playlists -- previously it only got filled in via the YT Music
            # metadata path below. But the user's chosen filename format (e.g.
            # the "Track # - Title" / "Album - Track # - Title" presets, or a
            # custom template) may reference %(track_number)s independently of
            # that experimental toggle. If we don't derive it here too, those
            # filenames silently fall back to "Unknown" for the track number
            # (see GH issue: track numbers only worked when "Fetch richer
            # metadata from YouTube Music" was also enabled). So: derive
            # track_number from playlist_index whenever the resolved filename
            # template needs it, regardless of YT_MUSIC_METADATA/is_yt_music.
            needs_track_number = "%(track_number)" in name_tmpl
            if is_playlist and not is_flat_playlist and (
                needs_track_number or (getattr(s, "YT_MUSIC_METADATA", False) and is_yt_music)
            ):
                # Track numbers only -- do NOT touch artist/title via regex.
                cmd.extend(["--parse-metadata", "playlist_index:%(track_number)s"])
        else:
            preferred = (getattr(s, "VIDEO_FORMAT", "").lstrip(".")) or "mkv"
            if preferred not in {"mkv", "mp4", "webm"}:
                preferred = "mkv"

            url = it.get("url", "") or ""
            chosen_format: Optional[str] = None

            # If user explicitly selected an hls- format code, use it directly
            if isinstance(format_code, str) and format_code.startswith("hls-"):
                chosen_format = format_code

            try:
                if not chosen_format and self._is_hls_preferred_site(url):
                    # IMPORTANT: by this point format_code has already been
                    # expanded from a simple "1440p" token into the full
                    # resolved format chain (e.g. from a RESOLUTIONS preset
                    # or get_format_for_resolution()), so it essentially
                    # never literally ends with "p" here -- checking for
                    # that (as before) silently dropped the user's chosen
                    # height entirely for HLS-preferred sites, and the
                    # resulting *unrestricted* HLS chain would just grab
                    # whatever muxed stream yt-dlp considered "best",
                    # capping out well below what was actually available
                    # (e.g. a 1440p/4K pick silently downloading 1080p60
                    # because that's the highest *muxed* HLS format
                    # YouTube exposes -- higher resolutions only exist as
                    # separate video-only DASH streams). Pull the intended
                    # height back out of the resolved chain via regex
                    # instead, and always try a normal (non-HLS) merge at
                    # that height before ever falling back to a
                    # resolution-capped muxed HLS stream.
                    height_matches = re.findall(r"height(?:<=|=)(\d+)", str(format_code))
                    height = max((int(h) for h in height_matches), default=None)
                    if height:
                        chosen_format = (
                            f"bestvideo[protocol^=m3u8][height<={height}]+bestaudio/"
                            f"bestvideo[height<={height}]+bestaudio/"
                            f"best[protocol^=m3u8][height<={height}]/best[protocol^=m3u8]/best"
                        )
                    else:
                        chosen_format = (
                            "bestvideo[protocol^=m3u8]+bestaudio/"
                            "bestvideo+bestaudio/"
                            "best[protocol^=m3u8]/best"
                        )

                    # Prefer ffmpeg for HLS and use mpegts container for compatibility
                    cmd.append("--hls-prefer-native")
                    cmd.append("--hls-use-mpegts")

                    # Add common headers that some HLS endpoints require
                    # Use site root as Referer; keep headers limited and only for HLS-preferred domains
                    try:
                        host = re.sub(r"^https?://", "", url.split("/")[2]) if "/" in url else ""
                        referer = f"https://{host}" if host else "https://example.com"
                    except Exception:
                        referer = "https://example.com"
                    cmd.extend(["--add-header", f"Referer: {referer}"])
                    cmd.extend(["--add-header", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)"])
            except Exception:
                chosen_format = None

            if not chosen_format:
                chosen_format = format_code or "best"

            # Presets picked straight from settings.RESOLUTIONS (e.g. an
            # itag pair like "251+313") don't always carry their own
            # "/best" fallback -- if that exact stream combo isn't offered
            # for a given video, yt-dlp fails hard with "Requested format
            # is not available" instead of degrading gracefully. Make sure
            # every video format selector we hand to yt-dlp ends in a
            # generic "best" so a missing preferred stream never hard-fails
            # the whole download.
            chosen_format = self._ensure_format_fallback(chosen_format)

            # --merge-output-format only takes effect when yt-dlp actually
            # merges two separately downloaded streams (e.g. bestvideo+
            # bestaudio). When yt-dlp instead picks a single already-muxed
            # / progressive stream (very common for YouTube, which usually
            # serves those as .mp4), no merge step runs and
            # --merge-output-format is silently ignored -- the file keeps
            # whatever container it was downloaded in, regardless of the
            # user's VIDEO_FORMAT preference. --remux-video forces a
            # container remux (ffmpeg stream copy, no re-encode) whenever
            # the result isn't already in the target container, so the
            # user's chosen format is honored in both the merge and
            # no-merge cases.
            cmd.extend([
                "-f", chosen_format,
                "--merge-output-format", preferred,
                "--remux-video", preferred,
            ])
            if getattr(s, "ADD_METADATA", False):
                cmd.append("--add-metadata")

        if getattr(s, "SPONSORBLOCK_CATEGORIES", None) and not self.is_short_video(it.get("url", "")):
            try:
                cats = ",".join(s.SPONSORBLOCK_CATEGORIES)
                cmd.extend(["--sponsorblock-remove", cats])
                cmd.extend(["--sleep-requests", "1", "--sleep-subtitles", "1"])
            except Exception:
                pass

        if getattr(s, "CHAPTERS_MODE", "none") == "split":
            cmd.append("--split-chapters")
        elif getattr(s, "CHAPTERS_MODE", "none") == "embed":
            cmd.append("--embed-chapters")

        if getattr(s, "WRITE_SUBS", False):
            cmd.append("--write-subs")
            if getattr(s, "SUB_LANGS", ""):
                cmd.extend(["--sub-langs", s.SUB_LANGS])
            if getattr(s, "WRITE_AUTO_SUBS", False):
                cmd.append("--write-auto-subs")
            if getattr(s, "CONVERT_SUBS_TO_SRT", False):
                cmd.extend(["--convert-subs", "srt"])

        if getattr(s, "WRITE_THUMBNAIL", False):
            cmd.append("--write-thumbnail")
        if getattr(s, "CONVERT_THUMBNAILS", False):
            fmt = getattr(s, "THUMBNAIL_FORMAT", "png") or "png"
            cmd.extend(["--convert-thumbnails", fmt])

        if getattr(s, "EMBED_THUMBNAIL", False) and not is_audio:
            self._add_log(f"🖼️ Will embed thumbnail as cover for: {self._short(it.get('title',''))}\n", AppStyles.INFO_COLOR)
            cmd.append("--embed-thumbnail")
            # NOTE: previously this also passed a custom
            # "EmbedThumbnail:-metadata:s:t mimetype=... filename=..."
            # via --postprocessor-args. EmbedThumbnailPP already sets this
            # metadata itself, and passing it explicitly here was found to
            # conflict with the new forced --remux-video step (VideoRemuxer
            # would fail with "Postprocessing: Conversion failed!" even
            # though the args were scoped to "EmbedThumbnail:"). Dropping
            # the custom postprocessor-args avoids the collision entirely;
            # --embed-thumbnail alone still produces correct mimetype/
            # filename metadata on the attachment.

        if getattr(s, "CUSTOM_FFMPEG_ARGS", ""):
            cmd.extend(["--postprocessor-args", f"ffmpeg:{s.CUSTOM_FFMPEG_ARGS}"])

        # If a Deno binary is available, instruct yt-dlp to use it for JS runtimes
        try:
            deno_path = getattr(s, "DENO_PATH", None)
            if deno_path and Path(deno_path).exists():
                cmd.extend(["--js-runtimes", f"deno:{str(deno_path)}"])
        except Exception:
            pass

        # SSL/CA handling (supports MITM-DomainFronting style local proxies
        # via a trusted custom CA cert, falling back to --no-check-certificates
        # only if no custom CA is configured)
        _verify, _ytdlp_ssl_args, self._ssl_env = ssl_utils.resolve_ssl_config(self.settings)
        cmd.extend(_ytdlp_ssl_args)

        cmd.append(it.get("url", ""))

        return [str(c) for c in cmd]

    @staticmethod
    def _ensure_format_fallback(fmt: str) -> str:
        """Guarantee a yt-dlp format-selector string ends with a generic
        "best" fallback so an unavailable specific stream (a particular
        itag/codec/height combo) degrades to "whatever's available" instead
        of hard-failing the download with "Requested format is not
        available"."""
        if not fmt:
            return "best"
        parts = [p.strip() for p in fmt.split("/") if p.strip()]
        if not parts:
            return "best"
        if parts[-1] != "best":
            parts.append("best")
        seen = set()
        deduped: List[str] = []
        for p in parts:
            if p not in seen:
                deduped.append(p)
                seen.add(p)
        return "/".join(deduped)

    # Built once at class-definition time instead of being rebuilt (string
    # join + regex compile) on every single completed download -- the
    # pattern list is static, so re-deriving it per call was pure waste.
    _MUSIC_VIDEO_TAG_TEXTS = (
        "(music video)", "(official video)", "(official visualizer)", "(video oficial)",
        "[official video]", "(drone)", "(video)", "(visualiser)", "(lyric video)", "(lyrics)",
        "(audio)", "(official track)", "(original mix)", "(hq)", "(hd)", "(high quality)",
        "(full song)", "(snippet)", "(reaction)", "(review)", "(trailer)", "(teaser)",
        "(fan edit)", "(studio version)", "(youtube)", "(vevo)", "(tiktok)",
        "(drone shot)", "(pov video)", "(official music video)", "(visualizer)",
        "(official lyric video)",
    )
    _MUSIC_VIDEO_TAG_RE = re.compile(
        r"\s*(?:" + "|".join(re.escape(t) for t in _MUSIC_VIDEO_TAG_TEXTS) + r")",
        re.IGNORECASE,
    )

    def _clean_music_video_tags(self) -> int:
        downloads_root: Path = Path(self.settings.DOWNLOADS_DIR)
        if not downloads_root.exists():
            return 0
        audio_exts = {".mp3", ".flac", ".opus"}
        combined = self._MUSIC_VIDEO_TAG_RE
        renamed = 0

        for root, _dirs, files in os.walk(downloads_root):
            for fname in files:
                p = Path(root) / fname
                if p.suffix.lower() not in audio_exts:
                    continue
                if not combined.search(fname):
                    continue
                new_stem = combined.sub("", p.stem)
                new_stem = re.sub(r"\s{2,}", " ", new_stem).strip(" -_.,")
                if not new_stem:
                    new_stem = p.stem
                new_name = f"{new_stem}{p.suffix}"
                new_path = p.with_name(new_name)
                if new_path == p:
                    continue
                if new_path.exists():
                    i = 1
                    while True:
                        candidate = p.with_name(f"{new_stem} ({i}){p.suffix}")
                        if not candidate.exists():
                            new_path = candidate
                            break
                        i += 1
                try:
                    p.rename(new_path)
                    renamed += 1
                    self._add_log(f"🧹 Renamed: {p.name} → {new_path.name}\n", AppStyles.INFO_COLOR)
                except Exception:
                    pass
        return renamed

    # Minimal, efficient logging helpers
    def _add_log(self, text: str, color: str):
        try:
            # keep buffer bounded
            if len(self._log_buffer) > 1500:
                del self._log_buffer[:700]
            self._log_buffer.append((text, color))
        except Exception:
            pass

    def _flush_logs(self):
        # Called in worker thread by timer or synchronously by other methods
        if not self._log_buffer:
            return
        try:
            buf = self._log_buffer[:]   # snapshot
            self._log_buffer.clear()
        except Exception:
            buf = []

        # Coalesce consecutive entries with the same color to reduce signal count.
        def _emit_pending(color: Optional[str], parts: List[str], emitted_bytes: int, emitted_entries: int):
            if not color or not parts:
                return emitted_bytes, emitted_entries
            combined = "\n".join(parts)
            try:
                self.log.emit(combined, color)
            except Exception:
                pass
            return emitted_bytes + len(combined.encode("utf-8")), emitted_entries + 1

        cur_text_parts: List[str] = []
        cur_color: Optional[str] = None
        emitted_bytes = 0
        emitted_entries = 0
        cutoff_idx: Optional[int] = None  # index into buf where we stopped, if capped

        for i, (text, color) in enumerate(buf):
            if emitted_entries >= self._max_entries_per_flush or emitted_bytes > self._max_emit_bytes:
                cutoff_idx = i
                break

            if cur_color is None:
                cur_color, cur_text_parts = color, [text]
            elif color == cur_color:
                cur_text_parts.append(text)
            else:
                emitted_bytes, emitted_entries = _emit_pending(cur_color, cur_text_parts, emitted_bytes, emitted_entries)
                cur_color, cur_text_parts = color, [text]

        if cutoff_idx is None:
            # Went through the whole buffer; emit whatever's left over.
            emitted_bytes, emitted_entries = _emit_pending(cur_color, cur_text_parts, emitted_bytes, emitted_entries)
        else:
            # Hit a cap mid-buffer: emit what we'd accumulated so far (if any),
            # then requeue everything from cutoff_idx onward, using the actual
            # position rather than a value-based lookup (which could match an
            # earlier, identical (text, color) pair and corrupt the buffer).
            emitted_bytes, emitted_entries = _emit_pending(cur_color, cur_text_parts, emitted_bytes, emitted_entries)
            remaining = buf[cutoff_idx:]
            if remaining:
                self._log_buffer[0:0] = remaining

    def _flush_logs_now(self):
        try:
            # direct synchronous flush; keep it safe
            self._flush_logs()
        except Exception:
            pass
