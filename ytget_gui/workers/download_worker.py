# File: ytget_gui/workers/download_worker.py
"""yt-dlp download worker.

Command construction is split into focused builders rather than one 300-line
method, and progress is parsed from an explicit --progress-template instead of
regex-scraping the human-readable progress bar.
"""

from __future__ import annotations

import codecs
import glob
import json
import shlex
import logging
import os
import re
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from PySide6.QtCore import QTimer, Signal

from ytget_gui import formats
from ytget_gui.settings import AppSettings, FILENAME_FORMAT_PRESETS
from ytget_gui.styles import AppStyles
from ytget_gui.utils.paths import is_usable_file, safe_stem
from ytget_gui.utils.text import short
from ytget_gui.utils.validators import (
    is_playlist_url,
    is_short_video_url,
    is_youtube_music_url,
    is_youtube_url,
)
from ytget_gui.workers import cookies as cookie_manager
from ytget_gui.workers import fetch_core, proc, ssl_utils
from ytget_gui.workers.base import CANCELLED_EXIT, BaseDownloadWorker

log = logging.getLogger(__name__)


def _as_positive_int(raw: Optional[str]) -> int:
    """Parse a progress-template field into a positive int, else 0.

    yt-dlp renders missing info fields as "NA", and a build that does not
    expand a key leaves the literal template text in place, so every
    non-numeric case has to degrade quietly to "unknown".
    """
    if not raw:
        return 0
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0

# Machine-readable progress. Scraping the rendered bar meant guessing which
# "43%" on a line was the download (vs. a fragment count or a postprocessor),
# and the ETA was read by string-splitting after the literal "ETA".
_PROGRESS_SENTINEL = "~~YTG~~"
# playlist_index/n_entries come from the info dict so the bar can advance
# across a playlist. Without them yt-dlp only reports per-file percentages,
# which made the bar run 0->100% once per track and reset for the next one.
_PROGRESS_TEMPLATE = (
    f"download:{_PROGRESS_SENTINEL}"
    "%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s"
    "|%(info.playlist_index)s|%(info.n_entries)s"
)
_PROGRESS_RE = re.compile(
    re.escape(_PROGRESS_SENTINEL)
    + r"\s*([\d.]+)%\|([^|]*)\|([^|\r\n]*)(?:\|([^|\r\n]*)\|([^|\r\n]*))?"
)
# Fallback for yt-dlp builds that do not honour the template keys.
_LEGACY_PERCENT_RE = re.compile(r"\[download\]\s+([\d.]+)%")
# yt-dlp announces each playlist entry before downloading it. This is the
# fallback source of playlist position for builds whose progress template does
# not expand the info fields above.
_PLAYLIST_ITEM_RE = re.compile(
    r"^\[download\]\s+Downloading item\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE
)

# yt-dlp's own progress markers, in the order it emits them. Each match
# supersedes the previous one, so the last hit is the final resting place of
# the file: Destination -> Merger -> ExtractAudio -> Remux -> MoveFiles.
_OUTPUT_PATTERNS = (
    re.compile(r"^\[download\]\s+Destination:\s*(?P<path>.+?)\s*$"),
    re.compile(r"^\[download\]\s+(?P<path>.+?)\s+has already been downloaded"),
    re.compile(r'^\[Merger\]\s+Merging formats into\s+"(?P<path>.+?)"'),
    re.compile(r"^\[ExtractAudio\]\s+Destination:\s*(?P<path>.+?)\s*$"),
    re.compile(r'^\[(?:VideoRemuxer|VideoConvertor)\][^"]*into\s+"(?P<path>.+?)"'),
    re.compile(r'^\[MoveFiles\]\s+Moving file\s+".+?"\s+to\s+"(?P<path>.+?)"'),
)

_FATAL_RE = re.compile(
    r"(Video unavailable"
    r"|This video is (?:private|unavailable)"
    r"|has been removed by the uploader"
    r"|account associated with this video has been terminated"
    r"|Sign in to confirm your age"
    r"|copyright (?:grounds|claim)"
    r"|is not available in your country"
    r"|This live event will begin in"
    r"|members-only content"
    r"|Private video"
    r"|Unsupported URL)",
    re.IGNORECASE,
)

_RETRYABLE_RE = re.compile(
    r"(HTTP Error 40[39]"
    r"|HTTP Error 429"
    r"|HTTP Error 5\d\d"
    r"|Requested format is not available"
    r"|Connection reset|Connection aborted|Remote end closed connection"
    r"|Read timed out|The read operation timed out"
    r"|Temporary failure in name resolution|Name or service not known"
    r"|unable to download video data"
    r"|unable to download webpage"
    r"|fragment .* not found"
    r"|Got error|urlopen error"
    r"|Broken pipe|EOF occurred in violation of protocol"
    r"|Sign in to confirm you.{0,3}re not a bot)",
    re.IGNORECASE,
)

# Sites that genuinely only serve usable streams over HLS can be opted into
# per-domain. YouTube is excluded unconditionally: it always exposes a full
# DASH ladder, and its muxed HLS renditions top out far below (often 1080p60
# when 1440p/4K exist as separate video-only DASH streams), so forcing HLS
# there silently downgrades quality no matter what the user configured.
_HLS_NEVER_DOMAINS = ("youtube.com", "youtu.be", "music.youtube.com")

_MUSIC_VIDEO_TAGS = (
    "(music video)", "(official video)", "(official music video)",
    "(official visualizer)", "(visualizer)", "(visualiser)", "(video oficial)",
    "[official video]", "(drone)", "(drone shot)", "(video)", "(pov video)",
    "(lyric video)", "(official lyric video)", "(lyrics)", "(audio)",
    "(official track)", "(original mix)", "(hq)", "(hd)", "(high quality)",
    "(full song)", "(snippet)", "(reaction)", "(review)", "(trailer)",
    "(teaser)", "(fan edit)", "(studio version)", "(youtube)", "(vevo)",
    "(tiktok)",
)
# Compiled at class-definition time: the pattern is static, so rebuilding it
# after every completed download was pure waste.
_MUSIC_VIDEO_RE = re.compile(
    r"\s*(?:" + "|".join(re.escape(t) for t in _MUSIC_VIDEO_TAGS) + r")",
    re.IGNORECASE,
)

_AUDIO_EXTENSIONS = frozenset({".mp3", ".flac", ".opus", ".m4a", ".ogg"})

# EBU R128 two-pass-equivalent single-pass normalisation. AUDIO_NORMALIZE was
# persisted, surfaced in Preferences and announced at startup in the previous
# revision but never reached the command line -- the setting did nothing.
_LOUDNORM_FILTER = "loudnorm=I=-14:TP=-1.5:LRA=11"

# Characters of subprocess output retained for error condensing / retry
# classification. Enough to hold a full yt-dlp traceback, small enough to be
# irrelevant to the process footprint.
_RECENT_OUTPUT_LIMIT = 8000


class DownloadWorker(BaseDownloadWorker):
    """Runs one yt-dlp invocation, with transparent retries for transient errors."""

    _raw_output = Signal(bytes)
    _process_exited = Signal(int)

    def __init__(
        self,
        item: Dict[str, Any],
        settings: AppSettings,
        **kwargs: Any,
    ) -> None:
        super().__init__(item, **kwargs)
        self.settings = settings

        self._process: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._proc_lock = threading.Lock()

        # Chunked reads can split a multi-byte UTF-8 sequence across reads.
        # Decoding each chunk independently mangled accented/CJK titles; an
        # incremental decoder holds the partial tail until the rest arrives.
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._line_tail = ""

        self._cmd: List[str] = []
        self._env: Dict[str, str] = {}
        # Rolling tail of yt-dlp output, kept for error condensing and retry
        # classification. Stored as chunks rather than one string: the previous
        # `(self._recent_output + text)[-8000:]` rebuilt an 8 KiB string on
        # every read from the subprocess (thousands of times per download),
        # which is pure copying on the hottest path in the app.
        self._recent_chunks: Deque[str] = deque()
        self._recent_len = 0
        # Declared here rather than being created on the fly inside
        # _build_command()/_resolve_output(). Those assignments only happened
        # on some branches, so readers such as _add_pp_args() and the
        # track-number check could hit AttributeError depending on the format
        # and URL combination.
        self._pp_args: Dict[str, List[str]] = {}
        self._flat_album_name = ""
        self._name_template = ""
        self._name_suffix = str(item.get("name_suffix") or "").strip()
        self._attempt = 0
        self._max_attempts = max(0, int(getattr(settings, "AUTO_RETRY_COUNT", 3) or 0))
        self._started_at = 0.0

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._launch)
        self._cancel_poll = QTimer(self)
        self._cancel_poll.setInterval(100)
        self._cancel_poll.timeout.connect(self._check_cancelled_retry)
        self._flat_playlist_dir: Optional[Path] = None
        self._is_audio = False
        self._outputs: List[str] = []

        # Video-only + audio-only formats (e.g. "399+251") download as two
        # separate yt-dlp streams that are merged afterwards. Each stream
        # reports its own 0-100% independently, so relaying it verbatim made
        # the bar climb to 100%, drop back down, and climb again for the
        # second file. These fields let us fold both streams into one
        # continuous 0-100% instead.
        self._expected_streams = 1
        self._stream_index = 0
        self._stream_starts_seen = 0

        # Playlist position, so a multi-entry download reports one continuous
        # 0-100% across the whole playlist rather than restarting per track.
        # 0 means "not a playlist / position unknown", which keeps the
        # single-file math a pass-through.
        self._playlist_index = 0
        self._playlist_total = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _start(self) -> None:
        self._raw_output.connect(self._on_output)
        self._process_exited.connect(self._on_exit)

        self._refresh_cookies_if_needed()

        if not Path(self.settings.YT_DLP_PATH).is_file():
            self.error.emit(
                f"yt-dlp not found at {self.settings.YT_DLP_PATH}. "
                "Install it via Help > Check for Updates."
            )
            self.emit_finished(2)
            return

        self._env = proc.tool_env(self.settings)
        self._cmd = self._build_command()
        self._started_at = time.time()

        self.add_log(f"\nStarting Download for: {self.title}", AppStyles.SUCCESS_COLOR)
        log.debug("Starting yt-dlp subprocess (arguments omitted for privacy)")
        self.flush_now()

        self._launch()

    def _launch(self) -> None:
        if self.cancelled:
            self.emit_finished(CANCELLED_EXIT)
            return

        self._cancel_poll.stop()
        self._reset_recent()
        self._line_tail = ""
        self._decoder.reset()
        self._stream_index = 0
        self._stream_starts_seen = 0
        self._playlist_index = 0
        self._playlist_total = 0
        self.reset_progress()

        try:
            process = proc.spawn(self._cmd, env=self._env)
        except FileNotFoundError:
            self.error.emit(f"yt-dlp not found at {self._cmd[0]}")
            self.emit_finished(2)
            return
        except OSError as exc:
            self.error.emit(f"Failed to start yt-dlp: {exc}")
            self.emit_finished(2)
            return

        with self._proc_lock:
            self._process = process

        if self.cancelled:
            # cancel() may have landed between the check above and the spawn.
            proc.terminate_tree(process)

        self._reader = threading.Thread(
            target=self._read_output, args=(process,), daemon=True,
            name="ytdlp-reader",
        )
        self._reader.start()

    def _check_cancelled_retry(self) -> None:
        if self.cancelled and self._retry_timer.isActive():
            self._retry_timer.stop()
            self._cancel_poll.stop()
            self.emit_finished(CANCELLED_EXIT)

    def _do_cancel(self) -> None:
        with self._proc_lock:
            process = self._process
        proc.terminate_tree(process)

    def _refresh_cookies_if_needed(self) -> None:
        s = self.settings
        if not (
            getattr(s, "COOKIES_AUTO_REFRESH", False)
            and getattr(s, "COOKIES_FROM_BROWSER", "")
        ):
            return
        _path, warning, _cancelled = fetch_core.maybe_refresh_cookies_interruptible(
            s, s.COOKIES_PATH, self._cancel_event)
        if warning:
            self.add_log(warning, AppStyles.WARNING_COLOR)

    # ------------------------------------------------------------------
    # Output handling
    # ------------------------------------------------------------------

    def _read_output(self, process: subprocess.Popen) -> None:
        """Runs on a reader thread; forwards bytes to the worker's thread."""
        stream = process.stdout
        if stream is None:
            self._process_exited.emit(CANCELLED_EXIT)
            return
        try:
            # 64 KiB reads: each emit crosses threads as a queued Qt event, and
            # the old 4 KiB size produced 16x the event traffic for the same
            # output, which is itself a source of GUI stutter.
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
            stream.close()
            self._process_exited.emit(code if code is not None else 2)

    def _on_output(self, data: bytes) -> None:
        text = self._decoder.decode(data)
        if not text:
            return

        self._record_recent(text)

        # Split into complete lines so a progress record straddling two reads
        # is still matched, and progress records never reach the console.
        buffer = self._line_tail + text
        lines = buffer.splitlines(keepends=False)
        if buffer and not buffer.endswith(("\n", "\r")):
            self._line_tail = lines.pop() if lines else buffer
        else:
            self._line_tail = ""

        for line in lines:
            if not self._handle_progress_line(line):
                self._log_line(line)

        if self._line_tail:
            # Progress with \r-only terminators arrives without a newline, so
            # inspect the partial tail too (but do not log it yet).
            self._handle_progress_line(self._line_tail, partial=True)

    def _handle_progress_line(self, line: str, *, partial: bool = False) -> bool:
        """Return True when the line was progress data (and must not be logged)."""
        match = _PROGRESS_RE.search(line)
        if match:
            percent = float(match.group(1))
            speed = match.group(2).strip()
            eta = match.group(3).strip()
            self._note_playlist_position(match.group(4), match.group(5))
            self._emit_weighted_progress(percent)
            parts = [self._stream_label(), f"{percent:.0f}%"]
            if speed and speed not in ("Unknown", "N/A", "--"):
                parts.append(speed)
            if eta and eta not in ("Unknown", "N/A", "--"):
                parts.append(f"ETA {eta}")
            self.emit_stage(" \u00b7 ".join(p for p in parts if p))
            return True

        legacy = _LEGACY_PERCENT_RE.search(line)
        if legacy:
            self._emit_weighted_progress(float(legacy.group(1)))
            return partial

        return False

    def _note_playlist_position(
        self, raw_index: Optional[str], raw_total: Optional[str]
    ) -> None:
        """Record which playlist entry yt-dlp is currently downloading.

        Values arrive as template text, so anything non-numeric ("NA" for a
        single video, or a literal placeholder on builds that do not expand
        the info fields) is ignored and leaves the single-file behaviour
        untouched.
        """
        index = _as_positive_int(raw_index)
        total = _as_positive_int(raw_total)
        if total:
            self._playlist_total = total
        if index and index != self._playlist_index:
            # New entry: its streams start over, so reset the per-item stream
            # counters or the second track would begin its bar at 50%.
            self._playlist_index = index
            self._stream_index = 0
            self._stream_starts_seen = 0

    def _emit_weighted_progress(self, stream_percent: float) -> None:
        """Fold a single stream's 0-100% into the item's overall 0-100%.

        With two streams (video + audio), stream_index 0 covers the first
        half of the bar and stream_index 1 the second half, so the bar rises
        continuously instead of completing once per stream. When only one
        stream is expected this is just a pass-through.

        For a playlist the result is then folded again into the playlist's
        own span: entry 3 of 25 at 50% of its second stream reports
        ((2 + 0.75) / 25) * 100 = 11%, so the bar advances monotonically to
        100% across the playlist instead of once per track.
        """
        n = max(1, self._expected_streams)
        stream_percent = max(0.0, min(100.0, stream_percent))
        fraction = (self._stream_index + stream_percent / 100.0) / n

        total = self._playlist_total
        index = self._playlist_index
        if total > 1 and index >= 1:
            fraction = (min(index, total) - 1 + fraction) / total

        self.emit_progress(int(max(0.0, min(1.0, fraction)) * 100.0))

    def _on_stream_start(self) -> None:
        """Called when a new "[download] Destination:" marker appears."""
        if self._stream_starts_seen > 0:
            self._stream_index = min(self._stream_starts_seen, self._expected_streams - 1)
        self._stream_starts_seen += 1

    def _stream_label(self) -> str:
        """Best-effort "Video"/"Audio" label for the stage line.

        yt-dlp lists the video-only format before the audio-only one in a
        selector like "399+251", and downloads them in that order, so the
        first stream is (almost always) video and the second is audio. This
        is a labelling heuristic only -- it never affects the percent math.
        """
        if self._expected_streams != 2 or self._is_audio:
            return ""
        return "Video" if self._stream_index == 0 else "Audio"

    def _log_line(self, line: str) -> None:
        stripped = line.strip()
        if not stripped:
            return
        item = _PLAYLIST_ITEM_RE.match(stripped)
        if item:
            # Keep the line in the console (it is useful context) but also use
            # it as the fallback source of playlist position.
            self._note_playlist_position(item.group(1), item.group(2))
        if stripped.startswith("~~YTGFILE~~"):
            try:
                path = json.loads(stripped[len("~~YTGFILE~~"):])
                if isinstance(path, str) and path not in self._outputs:
                    self._outputs.append(path)
            except (ValueError, TypeError):
                pass
            return
        self._capture_output(stripped)
        lowered = stripped.lower()
        if "error" in lowered:
            colour = AppStyles.ERROR_COLOR
        elif "warning" in lowered:
            colour = AppStyles.WARNING_COLOR
        else:
            colour = AppStyles.TEXT_COLOR
            # Routine yt-dlp chatter is opt-in (Preferences > Advanced >
            # Interface). Problems are never hidden: only plain output is
            # dropped, and the line is still parsed for the output path and
            # playlist position above.
            if not getattr(self.settings, "SHOW_YTDLP_LOGS", False):
                return
        self.add_log(stripped, colour)

    def _capture_output(self, line: str) -> None:
        """Record the produced file, so the queue card can open it later."""
        for index, pattern in enumerate(_OUTPUT_PATTERNS):
            match = pattern.match(line)
            if match is None:
                continue
            # The first two patterns ("Destination:" and "has already been
            # downloaded") each mark the start of one yt-dlp stream; the rest
            # (Merger, ExtractAudio, ...) are postprocessing steps that don't
            # represent a new download to weight progress against.
            if index < 2:
                self._on_stream_start()
            candidate = (match.group("path") or "").strip().strip('"')
            if not candidate:
                return
            # Intermediate streams (.f251.webm) and fragments are superseded by
            # a later marker; keeping them all lets the last one win.
            if candidate not in self._outputs:
                self._outputs.append(candidate)
            return

    def _resolve_output(self) -> Optional[Path]:
        """Best guess at the final file, verified against the filesystem.

        Later markers win, but a marker can name an intermediate that
        postprocessing has since removed, so unwind to the newest path that
        actually exists.
        """
        for candidate in reversed(self._outputs):
            try:
                path = Path(candidate)
                if path.is_file():
                    return path
            except OSError:
                continue

        # Every recorded path is gone: postprocessing changed the extension
        # without announcing it, or the cleanup pass renamed the file. Match on
        # the stem within the same folder.
        for candidate in reversed(self._outputs):
            try:
                stub = Path(candidate)
                folder = stub.parent
                if not folder.is_dir():
                    continue
                matches = sorted(
                    (p for p in folder.glob(f"{glob.escape(stub.stem)}.*") if p.is_file()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if matches:
                    return matches[0]
            except OSError:
                continue
        return None

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    def _on_exit(self, code: int) -> None:
        with self._proc_lock:
            self._process = None

        self._line_tail += self._decoder.decode(b"", final=True)
        if self._line_tail.strip():
            if not self._handle_progress_line(self._line_tail):
                self._log_line(self._line_tail)
            self._line_tail = ""
        self.flush()

        if self.cancelled:
            self.add_log("\u23f9\ufe0f Download cancelled by user.", AppStyles.WARNING_COLOR)
            self.emit_finished(CANCELLED_EXIT)
            return

        if code == 0:
            self._on_success()
            return

        if self._should_retry():
            self._schedule_retry(code)
            return

        self.add_log(
            f"\u274c yt-dlp exited with code {code}.", AppStyles.ERROR_COLOR
        )
        self.error.emit(fetch_core._condense_error(self._recent_output) or f"yt-dlp exited with code {code}")
        self.emit_finished(code if code > 0 else 2)

    def _on_success(self) -> None:
        self.emit_progress(100)
        self.add_log(
            "\u2705 Download finished successfully.", AppStyles.SUCCESS_COLOR
        )

        if self._flat_playlist_dir is not None:
            tagged = self._tag_flat_playlist_tracks()
            if tagged:
                self.add_log(
                    f"\U0001f522 Tagged track numbers on {tagged} file(s).",
                    AppStyles.SUCCESS_COLOR,
                )

        if self._is_audio:
            renamed = self._clean_music_video_tags()
            if renamed:
                self.add_log(
                    f"\u2728 Cleaned {renamed} filename(s).", AppStyles.SUCCESS_COLOR
                )

        final = self._resolve_output()
        if final is not None:
            self.emit_output(str(final), sum(Path(v).is_file() for v in self._outputs))
        elif self._flat_playlist_dir is not None and self._flat_playlist_dir.is_dir():
            # A flat playlist produces many files; the folder is the useful
            # thing to open.
            self.emit_output(str(self._flat_playlist_dir), len(self._outputs))

        self.emit_finished(0)

    # ------------------------------------------------------------------
    # Recent-output tail
    # ------------------------------------------------------------------

    def _record_recent(self, text: str) -> None:
        """Append to the bounded tail of subprocess output.

        Amortised O(len(text)) instead of O(_RECENT_OUTPUT_LIMIT) per chunk.
        """
        self._recent_chunks.append(text)
        self._recent_len += len(text)
        # Keep at least one chunk so a single oversized chunk is still readable.
        while self._recent_len > _RECENT_OUTPUT_LIMIT and len(self._recent_chunks) > 1:
            self._recent_len -= len(self._recent_chunks.popleft())

    def _reset_recent(self) -> None:
        self._recent_chunks.clear()
        self._recent_len = 0

    @property
    def _recent_output(self) -> str:
        """The tail as one string, materialised only when actually needed
        (error condensing and retry classification), not per read."""
        if not self._recent_chunks:
            return ""
        if len(self._recent_chunks) > 1:
            joined = "".join(self._recent_chunks)
            self._recent_chunks.clear()
            self._recent_chunks.append(joined)
            self._recent_len = len(joined)
        return self._recent_chunks[0]

    def _should_retry(self) -> bool:
        if self.cancelled or self._attempt >= self._max_attempts:
            return False
        text = self._recent_output
        if not text or _FATAL_RE.search(text):
            return False
        return bool(_RETRYABLE_RE.search(text))

    def _schedule_retry(self, code: int) -> None:
        """Re-run the whole command after a transient failure.

        --retries only covers in-process HTTP retries against the *same* signed
        URL. When that URL expires mid-download (the classic 403), only a fresh
        invocation helps, because it fetches a fresh URL.
        """
        self._attempt += 1
        delay = min(30.0, 3.0 * self._attempt)
        self.add_log(
            f"\u26a0\ufe0f Recoverable error (exit {code}); the request likely expired. "
            f"Retrying in {delay:.0f}s\u2026 "
            f"(attempt {self._attempt}/{self._max_attempts})",
            AppStyles.WARNING_COLOR,
        )
        self.flush_now()
        self._start_log_timer()
        self._retry_timer.start(int(delay * 1000))
        self._cancel_poll.start()

    # ------------------------------------------------------------------
    # Command construction
    # ------------------------------------------------------------------

    @staticmethod
    def _count_expected_streams(format_code: str) -> int:
        """How many separate yt-dlp downloads this selector will produce.

        "399+251" merges a video-only and an audio-only stream, so that's 2.
        A selector with fallbacks ("bv+ba/best") only ever resolves to one
        alternative at runtime, so only the first branch is counted.
        """
        if not format_code:
            return 1
        first_alt = format_code.split("/", 1)[0]
        return max(1, first_alt.count("+") + 1)

    def _build_command(self) -> List[str]:
        s = self.settings
        url = self.url

        format_code = s.resolve_format_code(self.item.get("format_code", ""))
        self._is_audio = formats.is_audio_code(format_code)
        self._expected_streams = self._count_expected_streams(format_code)
        is_playlist = bool(self.item.get("is_playlist")) or is_playlist_url(url) or format_code in formats.PLAYLIST_FORMAT_CODES

        # Assigned before any branch. Previously this was only bound inside the
        # non-flat-playlist branch yet read unconditionally further down, so the
        # YouTube Music "Top songs"/Mix/Radio path raised UnboundLocalError
        # inside _build_command and surfaced as "Error preparing download" --
        # meaning that feature could never have worked.
        is_yt_music = is_youtube_music_url(url)

        self._flat_playlist_dir = None
        self._pp_args: Dict[str, List[str]] = {}

        cmd: List[str] = [
            str(s.YT_DLP_PATH),
            "--ignore-config",
            "--no-overwrites",
            "--no-simulate",
            "--print", "after_move:~~YTGFILE~~%(filepath)j",
            "--newline",
            "--progress",
            "--progress-template", _PROGRESS_TEMPLATE,
            "--output-na-placeholder", "Unknown",
            "--ffmpeg-location", str(Path(s.FFMPEG_PATH).parent),
        ]

        cmd += self._network_flags()
        cmd += self._selection_flags(is_playlist)

        is_flat = self._detect_flat_playlist_if_needed(
            url, is_playlist=is_playlist, is_audio=self._is_audio, is_yt_music=is_yt_music
        )
        cmd += self._output_flags(
            is_playlist=is_playlist,
            is_audio=self._is_audio,
            is_yt_music=is_yt_music,
            is_flat=is_flat,
        )

        if self._is_audio:
            cmd += self._audio_flags(format_code, is_playlist=is_playlist, is_flat=is_flat)
        else:
            cmd += self._video_flags(format_code, url)

        cmd += self._postprocessing_flags()
        cmd += self._subtitle_flags()
        cmd += self._thumbnail_flags()
        cmd += self._runtime_flags()

        # Emit accumulated ffmpeg/postprocessor args once per postprocessor:
        # yt-dlp keeps only the last --postprocessor-args for a given key, so
        # issuing several for "ffmpeg:" silently discarded all but one (which is
        # how FLAC compression settings were losing out to the album-tag write).
        for name, args in self._pp_args.items():
            if args:
                prefix = f"{name}:" if name else ""
                cmd.extend(["--postprocessor-args", prefix + shlex.join(args)])

        cmd += self._extra_and_client_flags(url)
        cmd.extend(["--", url])
        return [str(part) for part in cmd]

    def _add_pp_args(self, postprocessor: str, *args: str) -> None:
        self._pp_args.setdefault(postprocessor, []).extend(args)

    def _network_flags(self) -> List[str]:
        s = self.settings
        flags: List[str] = []

        if is_usable_file(s.COOKIES_PATH):
            flags += ["--cookies", str(s.COOKIES_PATH)]
        elif getattr(s, "COOKIES_FROM_BROWSER", ""):
            flags += ["--cookies-from-browser", s.COOKIES_FROM_BROWSER]
        if getattr(s, "PROXY_URL", ""):
            flags += ["--proxy", s.PROXY_URL]
        if getattr(s, "LIMIT_RATE", ""):
            flags += ["--limit-rate", s.LIMIT_RATE]

        retries = str(int(getattr(s, "RETRIES", 10)))
        flags += [
            "--retries", retries,
            # Matching --fragment-retries explicitly stops yt-dlp falling back
            # to a different default for HLS/DASH fragment downloads.
            "--fragment-retries", retries,
            "--extractor-retries", retries,
            # Space the attempts out: hammering a 429 immediately never clears.
            "--retry-sleep", "linear=1::2",
            "--file-access-retries", "3",
        ]

        _verify, ssl_args, _env = ssl_utils.resolve_ssl_config(s)
        flags += ssl_args
        return flags

    def _selection_flags(self, is_playlist: bool) -> List[str]:
        s = self.settings
        flags: List[str] = []

        if getattr(s, "DATEAFTER", ""):
            flags += ["--dateafter", s.DATEAFTER]
        if getattr(s, "LIVE_FROM_START", False):
            flags.append("--live-from-start")
        if is_playlist:
            # One unavailable entry must not abandon the rest of the playlist.
            flags.append("--no-abort-on-error")
        if getattr(s, "PLAYLIST_REVERSE", False):
            flags.append("--playlist-reverse")
        if getattr(s, "PLAYLIST_ITEMS", ""):
            flags += ["--playlist-items", s.PLAYLIST_ITEMS]

        # A second format of a URL that is already in the archive would be
        # skipped outright ("has already been recorded in the archive"),
        # so a deliberate re-download in another quality ignores it. The
        # URL is already recorded, so nothing is lost by not re-recording.
        archive = None if self._name_suffix else s.archive_target()
        if archive is not None:
            flags += ["--download-archive", str(archive)]

        start = str(getattr(s, "CLIP_START", "") or "").strip()
        end = str(getattr(s, "CLIP_END", "") or "").strip()
        if start and end:
            # --force-keyframes-at-cuts re-encodes around the boundaries. Without
            # it yt-dlp cuts at the nearest preceding keyframe, so the clip
            # starts early and the requested range is not what lands on disk --
            # the reason clip extraction was disabled in the previous revision.
            flags += ["--download-sections", f"*{start}-{end}", "--force-keyframes-at-cuts"]

        return flags

    def _detect_flat_playlist_if_needed(
        self, url: str, *, is_playlist: bool, is_audio: bool, is_yt_music: bool
    ) -> bool:
        """Detect YouTube Music's auto-generated Top songs/Mix/Radio playlists.

        These carry no real per-track album, so they need an explicit album tag
        and filename-derived track numbers rather than yt-dlp's extraction.
        """
        if not (is_audio and is_playlist and is_yt_music):
            return False
        if not getattr(self.settings, "YT_MUSIC_METADATA", False):
            return False

        try:
            result = proc.run(
                [
                    str(self.settings.YT_DLP_PATH),
                    "--ignore-config",
                    "--flat-playlist",
                    "--playlist-items", "1",
                    "--print", "%(playlist_title)s",
                    url,
                ],
                env=self._env or None,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            log.debug("Flat-playlist probe failed: %s", exc)
            return False

        if result.returncode != 0:
            return False
        return result.stdout.strip() in ("Top songs", "Mix", "Radio")

    def _output_flags(
        self, *, is_playlist: bool, is_audio: bool, is_yt_music: bool, is_flat: bool
    ) -> List[str]:
        s = self.settings

        if is_flat:
            # Use the fetched title only. self.title falls back to the URL when
            # metadata has not arrived yet, which named the folder and the album
            # tag after the web address; 2.7.9 read item["title"] here and fell
            # back to "Playlist".
            fetched_title = str(self.item.get("title") or "").strip()
            album = safe_stem(fetched_title or "Playlist") + " Playlist"
            base = Path(s.DOWNLOADS_DIR) / album
            # A literal "%" in a title would be parsed by yt-dlp as an output
            # template field, so escape it for -o while keeping the real name
            # for the on-disk path and the album tag.
            template_base = Path(s.DOWNLOADS_DIR) / album.replace("%", "%%")
            stub = self._resolve_name_template("%(album)s - %(title)s")
            filename = f"%(autonumber)03d - {stub}.%(ext)s"
            self._flat_playlist_dir = base
            self._flat_album_name = album
            self._name_template = stub
        else:
            base = Path(s.DOWNLOADS_DIR)
            if is_playlist:
                base = base / "%(playlist_title)s"
            if getattr(s, "ORGANIZE_BY_UPLOADER", False):
                base = base / "%(uploader)s"

            if getattr(s, "YT_MUSIC_METADATA", False) and is_yt_music and (
                is_audio or is_playlist
            ):
                default_stub = "%(artist)s - %(title)s"
            else:
                default_stub = "%(title)s"

            stub = self._resolve_name_template(default_stub)
            self._name_template = stub

            # Only set when another queued item for this URL already
            # targets the same container, so single items keep the plain
            # "%(title)s.%(ext)s" naming.
            tag = f" {self._name_suffix}" if self._name_suffix else ""
            if (
                self._should_force_title(is_playlist)
                and getattr(s, "FILENAME_FORMAT", "default") == "default"
            ):
                # No cookies means yt-dlp may resolve a degraded title; prefer
                # the one already shown in the queue so the file matches the UI.
                forced = safe_stem(self.title + tag).replace("%", "%%")
                filename = forced + ".%(ext)s"
            else:
                filename = f"{stub}{tag}.%(ext)s"
            self._flat_album_name = ""
            # base here intentionally contains yt-dlp template fields such as
            # %(playlist_title)s, so it must not be escaped.
            template_base = base

        flags = ["-o", str(template_base / filename)]
        if is_playlist:
            flags.insert(0, "--yes-playlist")
        else:
            flags.insert(0, "--no-playlist")
        return flags

    def _should_force_title(self, is_playlist: bool) -> bool:
        s = self.settings
        if is_playlist:
            return False
        has_cookies = is_usable_file(s.COOKIES_PATH) or bool(
            getattr(s, "COOKIES_FROM_BROWSER", "")
        )
        return not has_cookies and bool(self.item.get("title"))

    def _resolve_name_template(self, default_template: str) -> str:
        s = self.settings
        fmt = getattr(s, "FILENAME_FORMAT", "default") or "default"
        if fmt == "default":
            return default_template
        if fmt == "custom":
            custom = (getattr(s, "CUSTOM_FILENAME_TEMPLATE", "") or "").strip()
            return custom or default_template
        return FILENAME_FORMAT_PRESETS.get(fmt, default_template)

    def _audio_flags(
        self, format_code: str, *, is_playlist: bool, is_flat: bool
    ) -> List[str]:
        s = self.settings

        if format_code == "audio_flac":
            audio_format = "flac"
        elif format_code in ("audio_opus", "playlist_opus"):
            audio_format = "opus"
        else:
            audio_format = "mp3"

        flags = [
            "-f", formats.audio_chain(),
            "--extract-audio",
            "--audio-format", audio_format,
        ]
        if getattr(s, "ADD_METADATA", True):
            flags.append("--add-metadata")
        if audio_format == "mp3":
            # --audio-quality is a VBR scale for lossy encoders; passing it for
            # FLAC/Opus is meaningless and Opus interprets 0 as a bitrate.
            flags += ["--audio-quality", "0"]

        if audio_format == "flac":
            self._add_pp_args("ffmpeg", "-compression_level", "12")
        if getattr(s, "AUDIO_NORMALIZE", False):
            self._add_pp_args("ffmpeg", "-af", _LOUDNORM_FILTER)
        if is_flat and self._flat_album_name:
            self._add_pp_args("ffmpeg", "-metadata", f"album={self._flat_album_name}")

        # %(track_number)s is not populated by yt-dlp on its own. It previously
        # only got derived when the YouTube Music toggle was on, so the
        # "Track # - Title" presets silently produced "Unknown" for everyone
        # else. Derive it whenever the resolved template actually needs it.
        needs_track_number = "%(track_number)" in getattr(self, "_name_template", "")
        if is_playlist and not is_flat and (
            needs_track_number
            or (getattr(s, "YT_MUSIC_METADATA", False))
        ):
            flags += ["--parse-metadata", "playlist_index:%(track_number)s"]

        return flags

    def _video_flags(self, format_code: str, url: str) -> List[str]:
        s = self.settings
        container = (getattr(s, "VIDEO_FORMAT", ".mkv") or ".mkv").lstrip(".")
        if container not in ("mkv", "mp4", "webm"):
            container = "mkv"

        selector: Optional[str] = None
        native_hls = False

        if isinstance(format_code, str) and format_code.startswith("hls-"):
            selector = format_code
            native_hls = True
        elif self._prefers_hls(url):
            native_hls = True
            # format_code has already been expanded into a full selector chain
            # by this point, so it never literally ends in "p". The previous
            # revision tested for that suffix, so the user's chosen height was
            # dropped entirely for HLS-preferred sites and an unrestricted HLS
            # chain grabbed whatever muxed stream yt-dlp called "best".
            height = formats.max_height_in(format_code)
            selector = formats.hls_chain(height)

        if selector is None:
            selector = format_code or "best"
        selector = formats.ensure_best_fallback(selector)

        flags = ["-f", selector]

        if native_hls:
            flags += ["--hls-prefer-native", "--hls-use-mpegts"]
            referer = self._referer_for(url)
            flags += [
                "--add-header", f"Referer: {referer}",
                "--add-header",
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
            ]
            if container != "mp4":
                # ffmpeg's mkv muxer stream-copies raw HLS .ts unreliably: it can
                # keep only the embedded cover image and drop the real A/V
                # streams. Keep the mp4 yt-dlp produces naturally instead of
                # running that fragile remux.
                self.add_log(
                    "\u2139\ufe0f HLS source detected \u2014 keeping .mp4 instead of remuxing "
                    f"to .{container} (avoids an ffmpeg mkv-from-HLS stream-copy "
                    "bug that can leave only cover art).",
                    AppStyles.INFO_COLOR,
                )
        else:
            # --merge-output-format only applies when two streams are merged.
            # For an already-muxed progressive stream no merge runs and it is
            # silently ignored, so the container preference was not honoured;
            # --remux-video forces a stream-copy remux in that case too.
            flags += [
                "--merge-output-format", container,
                "--remux-video", container,
            ]

        if getattr(s, "ADD_METADATA", True):
            flags.append("--add-metadata")
        if getattr(s, "AUDIO_NORMALIZE", False):
            self._add_pp_args("ffmpeg", "-af", _LOUDNORM_FILTER)

        return flags

    def _prefers_hls(self, url: str) -> bool:
        s = self.settings
        if not getattr(s, "PREFER_HLS", False):
            return False
        from urllib.parse import urlsplit
        host = (urlsplit(url).hostname or "").lower()
        def matches(domain):
            domain = str(domain).lower().strip().lstrip(".")
            return bool(domain) and (host == domain or host.endswith("." + domain))
        if any(matches(d) for d in _HLS_NEVER_DOMAINS):
            return False
        return any(matches(d) for d in (s.HLS_PREFERRED_DOMAINS or []))

    @staticmethod
    def _referer_for(url: str) -> str:
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}/"
        except ValueError:
            pass
        return "https://example.com/"

    def _postprocessing_flags(self) -> List[str]:
        s = self.settings
        flags: List[str] = []

        categories = getattr(s, "SPONSORBLOCK_CATEGORIES", None)
        if categories and not is_short_video_url(self.url):
            flags += ["--sponsorblock-remove", ",".join(categories)]
            flags += ["--sleep-requests", "1"]

        mode = getattr(s, "CHAPTERS_MODE", "none")
        if mode == "split":
            flags.append("--split-chapters")
        elif mode == "embed":
            flags.append("--embed-chapters")

        custom = (getattr(s, "CUSTOM_FFMPEG_ARGS", "") or "").strip()
        if custom:
            self._add_pp_args("ffmpeg", *fetch_core.parse_extra_args(custom))

        return flags

    def _subtitle_flags(self) -> List[str]:
        s = self.settings
        if not getattr(s, "WRITE_SUBS", False):
            return []
        flags = ["--write-subs"]
        if getattr(s, "SUB_LANGS", ""):
            flags += ["--sub-langs", s.SUB_LANGS]
        if getattr(s, "WRITE_AUTO_SUBS", False):
            flags.append("--write-auto-subs")
        if getattr(s, "CONVERT_SUBS_TO_SRT", False):
            flags += ["--convert-subs", "srt"]
        return flags

    def _thumbnail_flags(self) -> List[str]:
        s = self.settings
        flags: List[str] = []
        if getattr(s, "WRITE_THUMBNAIL", False):
            flags.append("--write-thumbnail")
        if getattr(s, "CONVERT_THUMBNAILS", False):
            flags += ["--convert-thumbnails", getattr(s, "THUMBNAIL_FORMAT", "png") or "png"]
        # Audio always gets its cover art embedded, matching 2.7.9 where the
        # audio branch passed --embed-thumbnail unconditionally. The 2.8.x
        # refactor moved thumbnail handling here but kept only the video
        # gate, so every extracted MP3/FLAC/Opus silently lost its cover.
        # EMBED_THUMBNAIL stays the switch for *video* files only.
        if self._is_audio or getattr(s, "EMBED_THUMBNAIL", False):
            # EmbedThumbnailPP writes mimetype/filename metadata itself. The
            # previous revision also passed those explicitly via
            # --postprocessor-args, which collided with --remux-video and made
            # VideoRemuxer fail with "Postprocessing: Conversion failed!".
            flags.append("--embed-thumbnail")
        return flags

    def _runtime_flags(self) -> List[str]:
        deno = getattr(self.settings, "DENO_PATH", None)
        if deno and Path(deno).is_file():
            return ["--js-runtimes", f"deno:{deno}"]
        return []

    def _extra_and_client_flags(self, url: str) -> List[str]:
        s = self.settings
        extra = fetch_core.parse_ytdlp_args(getattr(s, "EXTRA_YTDLP_ARGS", ""))

        flags: List[str] = []
        player_client = str(getattr(s, "YOUTUBE_PLAYER_CLIENT", "auto") or "auto").strip()
        # yt-dlp keeps only the last --extractor-args for a given key, so if the
        # user set their own player_client we skip ours instead of overriding it.
        user_set = any(
            "youtube" in tok.lower() and "player_client" in tok.lower() for tok in extra
        )
        if player_client and player_client != "auto" and is_youtube_url(url) and not user_set:
            flags += ["--extractor-args", f"youtube:player_client={player_client}"]

        flags += extra
        return flags

    # ------------------------------------------------------------------
    # Post-download tidying
    # ------------------------------------------------------------------

    def _tag_flat_playlist_tracks(self) -> int:
        """Write track numbers derived from the "NNN - " filename prefix.

        yt-dlp cannot reliably map autonumber to track_number at postprocessing
        time in flat-playlist mode. This used to shell out to eyeD3 and silently
        did nothing when it was absent; mutagen is already a hard dependency, so
        the feature now works out of the box and covers FLAC/Opus too.
        """
        directory = self._flat_playlist_dir
        if directory is None or not directory.is_dir():
            return 0

        tagged = 0
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in _AUDIO_EXTENSIONS:
                continue
            token = path.name.split(" ", 1)[0]
            if not token.isdigit():
                continue
            if self._write_track_number(path, int(token)):
                tagged += 1
        return tagged

    @staticmethod
    def _write_track_number(path: Path, track: int) -> bool:
        try:
            import mutagen
            from mutagen.easyid3 import EasyID3
            from mutagen.id3 import ID3NoHeaderError

            suffix = path.suffix.lower()
            if suffix == ".mp3":
                try:
                    audio = EasyID3(path)
                except ID3NoHeaderError:
                    audio = EasyID3()
                    audio.filename = str(path)
                audio["tracknumber"] = str(track)
                audio.save(path)
                return True

            audio = mutagen.File(path)
            if audio is None:
                return False
            # FLAC/Opus/Vorbis use the TRACKNUMBER comment field.
            audio["tracknumber"] = str(track)
            audio.save()
            return True
        except Exception as exc:  # noqa: BLE001 - tagging is best-effort
            log.debug("Could not tag %s: %s", path, exc)
            return False

    def _rename_candidates(self, root: Path):
        """Yield the files worth inspecting for a post-download rename.

        This job already recorded every file it produced, so the directories
        holding those files are the only places a new audio file can appear.
        Listing just those directories keeps the cost proportional to this
        download instead of to the size of the user's whole library, which is
        what a recursive walk of DOWNLOADS_DIR cost on every single item.

        Falls back to one recursive walk only when no output path was captured
        (older yt-dlp builds that do not support the print template), so the
        previous behaviour is preserved rather than silently lost.
        """
        dirs: list[Path] = []
        seen: set[Path] = set()

        def add(candidate: Optional[Path]) -> None:
            if candidate is None:
                return
            try:
                resolved = candidate.resolve()
            except OSError:
                resolved = candidate
            if resolved in seen or not resolved.is_dir():
                return
            seen.add(resolved)
            dirs.append(resolved)

        for raw in self._outputs:
            add(Path(raw).parent)
        add(self._flat_playlist_dir)

        if not dirs:
            yield from root.rglob("*")
            return

        for directory in dirs:
            try:
                yield from directory.iterdir()
            except OSError as exc:
                log.debug("Could not list %s: %s", directory, exc)

    def _clean_music_video_tags(self) -> int:
        """Strip "(Official Video)"-style noise from freshly downloaded audio.

        Scoped to files whose mtime is at or after this job's start. The previous
        revision walked the entire download tree after every single item, so a
        large library cost a full recursive scan per download and, worse, could
        rename pre-existing files the user never asked it to touch.
        """
        root = Path(self.settings.DOWNLOADS_DIR)
        if not root.is_dir():
            return 0

        cutoff = self._started_at - 5  # small slack for clock/fs granularity
        renamed = 0

        for path in self._rename_candidates(root):
            if path.suffix.lower() not in _AUDIO_EXTENSIONS or not path.is_file():
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    continue
            except OSError:
                continue
            if not _MUSIC_VIDEO_RE.search(path.name):
                continue

            stem = _MUSIC_VIDEO_RE.sub("", path.stem)
            stem = re.sub(r"\s{2,}", " ", stem).strip(" -_.,") or path.stem
            target = path.with_name(f"{stem}{path.suffix}")
            if target == path:
                continue

            counter = 1
            while target.exists():
                target = path.with_name(f"{stem} ({counter}){path.suffix}")
                counter += 1

            try:
                path.rename(target)
            except OSError as exc:
                log.debug("Could not rename %s: %s", path, exc)
                continue

            renamed += 1
            # Keep the recorded output in step with the rename, or Play opens a
            # path that no longer exists.
            self._outputs = [
                str(target) if Path(p) == path else p for p in self._outputs
            ]
            if str(target) not in self._outputs:
                self._outputs.append(str(target))
            self.add_log(
                f"\U0001f9f9 Renamed: {short(path.name, 60)} \u2192 {short(target.name, 60)}",
                AppStyles.INFO_COLOR,
            )

        return renamed
