# File: ytget_gui/workers/download_worker.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QProcess, QTimer, QProcessEnvironment
import os
import re
import time

from ytget_gui.styles import AppStyles
from ytget_gui.settings import AppSettings


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

    def __init__(self, item: Dict[str, Any], settings: AppSettings, log_flush_ms: int = 3000, status_throttle_ms: int = 2000):
        super().__init__()
        self.item = item
        self.settings = settings
        self.process: Optional[QProcess] = None
        self._cancel_requested = False

        # small bounded buffer and timer created in run to belong to worker thread
        self._log_buffer: List[Tuple[str, str]] = []
        self._log_timer: Optional[QTimer] = None
        self._log_flush_ms = max(200, int(log_flush_ms))

        # lightweight compiled patterns
        # Look for percent tokens like "12.3%" or "12 %" near the download progress
        self._percent_re = re.compile(r"([0-9]{1,3}(?:[.,][0-9]+)?)\s*%")
        # Look for "[download]" prefix which yt-dlp commonly prints for progress lines
        self._download_tag = "[download]"
        # quick lowercase error check
        self._error_sub = "error"

        # throttle status emits
        self._last_status_text: Optional[str] = None
        self._last_status_emit = 0.0
        self._status_throttle_s = max(0.05, status_throttle_ms / 1000.0)

    # run should be invoked in a worker thread via moveToThread
    def run(self):
        try:
            # create timer with self as parent so it lives in this object's thread
            if self._log_timer is None:
                self._log_timer = QTimer(self)
                self._log_timer.setInterval(self._log_flush_ms)
                self._log_timer.timeout.connect(self._flush_logs)
                self._log_timer.start()

            cmd = self._build_command()

            # Build a minimal environment for the child process only
            env = None
            try:
                env = QProcessEnvironment.systemEnvironment()
                extras: List[str] = []
                if getattr(self.settings, "INTERNAL_DIR", None):
                    extras.append(str(self.settings.INTERNAL_DIR))
                if getattr(self.settings, "BASE_DIR", None):
                    extras.append(str(self.settings.BASE_DIR))
                ph = getattr(self.settings, "PHANTOMJS_PATH", None)
                if ph and hasattr(ph, "exists"):
                    try:
                        if ph.exists():
                            extras.append(str(ph.parent))
                    except Exception:
                        pass
                if extras:
                    cur = env.value("PATH", os.environ.get("PATH", ""))
                    parts = cur.split(os.pathsep) if cur else []
                    for p in reversed(extras):
                        if p and p not in parts:
                            parts.insert(0, p)
                    env.insert("PATH", os.pathsep.join(parts))
            except Exception:
                env = None

            # startup log and immediate flush so GUI sees it
            self._add_log(f"🚀 Starting Download for: {self._short(self.item.get('title',''))}\n", AppStyles.INFO_COLOR)
            self._flush_logs_now()

            # Setup QProcess
            self.process = QProcess(self)
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            if env is not None:
                self.process.setProcessEnvironment(env)
            self.process.readyReadStandardOutput.connect(self._on_read)
            self.process.errorOccurred.connect(self._on_qprocess_error)
            self.process.finished.connect(self._on_finished)

            program = cmd[0]
            args = cmd[1:]
            self.process.start(program, args)

            # short wait to detect immediate failures
            if not self.process.waitForStarted(4000):
                self.error.emit("Failed to start yt-dlp process.")
                self._flush_logs_now()
                try:
                    if self.process.state() == QProcess.Running:
                        self.process.kill()
                except Exception:
                    pass
                self.finished.emit(-1)
                return
        except Exception as e:
            self.error.emit(f"Error preparing download: {e}")
            self._flush_logs_now()
            self.finished.emit(-1)

    def cancel(self):
        self._cancel_requested = True
        if self.process and self.process.state() == QProcess.Running:
            self._add_log("⏹️ Cancelling Download...\n", AppStyles.WARNING_COLOR)
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

    # lightweight read handler that extracts and throttles progress info
    def _on_read(self):
        p = self.process
        if not p:
            return
        try:
            data = p.readAllStandardOutput().data()
            if not data:
                return
            text = data.decode(errors="ignore")

            # quick error detection with lower() to avoid regex unless needed
            is_error = self._error_sub in text.lower()
            color = AppStyles.ERROR_COLOR if is_error else AppStyles.TEXT_COLOR
            # append chunk as-is to minimize splitting cost
            self._add_log(text, color)

            # attempt progress extraction only if there's a percent token or download tag
            tail = text[-200:]  # small window where progress appears
            if (self._download_tag in tail) or ("%" in tail):
                # find last percent occurrence in tail
                m = self._percent_re.search(tail)
                pct_text: Optional[str] = None
                if m:
                    try:
                        pct_val = int(float(m.group(1).replace(",", ".")))
                        pct_text = f"{pct_val}%"
                    except Exception:
                        pct_text = m.group(1) + "%"

                # try to find simple ETA token after "ETA"
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

            # keep buffer bounded; flush if large
            if len(self._log_buffer) > 800:
                self._flush_logs()
        except Exception:
            # swallow to keep worker running
            pass

    def _on_qprocess_error(self, _code):
        self._add_log("❌ yt-dlp encountered a process error.\n", AppStyles.ERROR_COLOR)
        self._flush_logs_now()

    def _on_finished(self, exit_code: int, _status):
        try:
            if self._log_timer and self._log_timer.isActive():
                self._log_timer.stop()
        except Exception:
            pass

        # final flush
        try:
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
                if self._is_audio_download():
                    cleaned = self._clean_music_video_tags()
                    if cleaned > 0:
                        self._add_log(f"✨ Cleaned {cleaned} filename(s).\n", AppStyles.SUCCESS_COLOR)
                        self._flush_logs_now()
            except Exception:
                pass
            self.finished.emit(0)
        else:
            self._add_log(f"❌ yt-dlp exited with code {exit_code}.\n", AppStyles.ERROR_COLOR)
            self._flush_logs_now()
            self.finished.emit(exit_code)

    # --- Helpers ---
    def _post_finish_cleanup(self):
        try:
            if self._is_audio_download():
                cleaned = self._clean_music_video_tags()
                if cleaned > 0:
                    self._add_log(f"✨ Cleaned {cleaned} filename(s).\n", AppStyles.SUCCESS_COLOR)
        except Exception:
            pass

    def _short(self, title: str) -> str:
        title = title or ""
        return title[:50] + "..." if len(title) > 50 else title

    @staticmethod
    def is_short_video(url: str) -> bool:
        return "youtube.com/shorts/" in (url or "")

    def _is_audio_download(self) -> bool:
        code = self.item.get("format_code", "")
        return code in ("bestaudio", "playlist_mp3", "youtube_music", "audio_flac")

    def _should_force_title(self, is_playlist: bool) -> bool:
        s = self.settings
        try:
            no_cookie = not (s.COOKIES_PATH.exists() and s.COOKIES_PATH.stat().st_size > 0)
            no_browser = not bool(getattr(s, "COOKIES_FROM_BROWSER", None))
            return (not is_playlist) and no_cookie and no_browser
        except Exception:
            return (not is_playlist)

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
            "--progress",
            "--newline",
            "--output-na-placeholder", "Unknown",
            "--ffmpeg-location", str(s.FFMPEG_PATH.parent),
        ]

        format_code = it.get("format_code", "")
        is_playlist = "list=" in it.get("url", "") or format_code in ("playlist_mp3", "youtube_music")
        is_audio = self._is_audio_download()
        is_flac = (format_code == "audio_flac")

        if s.COOKIES_PATH.exists() and s.COOKIES_PATH.stat().st_size > 0:
            cmd.extend(["--cookies", str(s.COOKIES_PATH)])
        if getattr(s, "COOKIES_FROM_BROWSER", None):
            cmd.extend(["--cookies-from-browser", s.COOKIES_FROM_BROWSER])
        if getattr(s, "PROXY_URL", ""):
            cmd.extend(["--proxy", s.PROXY_URL])
        if getattr(s, "LIMIT_RATE", ""):
            cmd.extend(["--limit-rate", s.LIMIT_RATE])
        cmd.extend(["--retries", str(getattr(s, "RETRIES", 10))])

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

        if is_playlist:
            base = Path(s.DOWNLOADS_DIR) / "%(playlist_title)s"
            if getattr(s, "ORGANIZE_BY_UPLOADER", False):
                base /= "%(uploader)s"
        else:
            base = Path(s.DOWNLOADS_DIR)
            if getattr(s, "ORGANIZE_BY_UPLOADER", False):
                base /= "%(uploader)s"

        if getattr(s, "YT_MUSIC_METADATA", False) and (is_audio or is_playlist):
            fallback = "%(artist)s - %(title)s.%(ext)s"
        else:
            fallback = "%(title)s.%(ext)s"

        if self._should_force_title(is_playlist):
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
            cmd.extend([
                "-f", "bestaudio",
                "--extract-audio",
                "--audio-format", "flac" if is_flac else "mp3",
                "--embed-thumbnail",
            ])
            if getattr(s, "ADD_METADATA", False):
                cmd.append("--add-metadata")
            if not is_flac:
                cmd.extend(["--audio-quality", "0"])
            if is_flac:
                cmd.extend(["--postprocessor-args", "ffmpeg:-compression_level 12 -sample_fmt s16"])
            if format_code == "youtube_music" and getattr(s, "YT_MUSIC_METADATA", False):
                cmd.extend([
                    "--parse-metadata", "description:(?s)(?P<meta_comment>.+)",
                    "--parse-metadata", "%(meta_comment)s:(?P<artist>[^\n]+)",
                    "--parse-metadata", "%(meta_comment)s:.+ - (?P<title>[^\n]+)",
                ])
        else:
            preferred = (getattr(s, "VIDEO_FORMAT", "").lstrip(".")) or "mkv"
            if preferred not in {"mkv", "mp4", "webm"}:
                preferred = "mkv"
            cmd.extend(["-f", format_code or "best", "--merge-output-format", preferred])
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
            fmt = getattr(s, "THUMBNAIL_FORMAT", "png") or "png"
            meta = f"ffmpeg:-metadata:s:t mimetype=image/{fmt} -metadata:s:t filename=cover.{fmt}"
            cmd.extend(["--postprocessor-args", meta])

        if getattr(s, "CUSTOM_FFMPEG_ARGS", ""):
            cmd.extend(["--postprocessor-args", f"ffmpeg:{s.CUSTOM_FFMPEG_ARGS}"])

        cmd.append(it.get("url", ""))

        return [str(c) for c in cmd]

    def _clean_music_video_tags(self) -> int:
        downloads_root: Path = Path(self.settings.DOWNLOADS_DIR)
        if not downloads_root.exists():
            return 0
        audio_exts = {".mp3", ".flac"}
        tag_texts = [
            "(music video)", "(official video)", "(official visualizer)", "(video oficial)",
            "[official video]", "(drone)", "(video)", "(visualiser)", "(lyric video)", "(lyrics)",
            "(audio)", "(official track)", "(original mix)", "(hq)", "(hd)", "(high quality)",
            "(full song)", "(snippet)", "(reaction)", "(review)", "(trailer)", "(teaser)",
            "(fan edit)", "(studio version)", "(youtube)", "(vevo)", "(tiktok)",
            "(drone shot)", "(pov video)", "(official music video)", "(visualizer)",
        ]
        escaped = "|".join(re.escape(t) for t in tag_texts)
        combined = re.compile(r"\s*(?:" + escaped + r")", re.IGNORECASE)
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
        for text, color in buf:
            try:
                self.log.emit(text, color)
            except Exception:
                pass

    def _flush_logs_now(self):
        try:
            self._flush_logs()
        except Exception:
            pass
