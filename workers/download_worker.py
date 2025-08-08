# File: ytget/workers/download_worker.py
from __future__ import annotations
from time import sleep
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, QProcess

from ytget.styles import AppStyles
from ytget.settings import AppSettings

@dataclass
class QueueItem:
    url: str
    title: str
    format_code: str

class DownloadWorker(QObject):
    log = Signal(str, str)     # text, color
    finished = Signal(int)     # exit code
    error = Signal(str)

    def __init__(self, item: Dict[str, Any], settings: AppSettings):
        super().__init__()
        self.item = item
        self.settings = settings
        self.process: Optional[QProcess] = None
        self._cancel_requested = False

    def run(self):
        try:
            cmd = self._build_command()
            self.log.emit(f"🚀 Starting download for: {self._short(self.item['title'])}\n", AppStyles.INFO_COLOR)
            self.process = QProcess()
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            self.process.readyReadStandardOutput.connect(self._on_read)
            self.process.errorOccurred.connect(self._on_error)
            self.process.finished.connect(self._on_finished)
            self.process.start(cmd[0], cmd[1:])
            if not self.process.waitForStarted(5000):
                self.error.emit("Failed to start yt-dlp process.")
                self.finished.emit(-1)
        except Exception as e:
            self.error.emit(f"Error preparing download: {e}")
            self.finished.emit(-1)

    def cancel(self):
        self._cancel_requested = True
        if self.process and self.process.state() == QProcess.Running:
            self.log.emit("⏹️ Cancelling download...\n", AppStyles.WARNING_COLOR)
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()

    def _on_read(self):
        if not self.process:
            return
        text = self.process.readAllStandardOutput().data().decode(errors="ignore")
        color = AppStyles.ERROR_COLOR if "error" in text.lower() else AppStyles.TEXT_COLOR
        self.log.emit(text, color)

    def _on_error(self, _code):
        self.log.emit("❌ yt-dlp encountered an error.\n", AppStyles.ERROR_COLOR)

    def _on_finished(self, exit_code: int, _status):
        if self._cancel_requested:
            self.log.emit("⏹️ Download cancelled by user.\n", AppStyles.WARNING_COLOR)
            self.finished.emit(-1)
            return
        if exit_code == 0:
            self.log.emit("✅ Download finished successfully.\n", AppStyles.SUCCESS_COLOR)
        else:
            self.log.emit(f"❌ yt-dlp exited with code {exit_code}.\n", AppStyles.ERROR_COLOR)
        self.finished.emit(exit_code)

    def _short(self, title: str) -> str:
        return title[:35] + "..." if len(title) > 35 else title

    def is_short_video(url: str) -> bool:
        return "youtube.com/shorts/" in url

    def _build_command(self) -> List[str]:
        s = self.settings
        it = self.item
        cmd: List[str] = [str(s.YT_DLP_PATH), "--no-warnings", "--progress", "--ffmpeg-location", str(s.FFMPEG_PATH.parent)]

        format_code = it["format_code"]
        is_playlist = "list=" in it["url"] or format_code in ("playlist_mp3", "youtube_music")
        is_audio = format_code in ("bestaudio", "playlist_mp3", "youtube_music")

        # Cookies / proxy / retries / rate
        if s.COOKIES_PATH.exists() and s.COOKIES_PATH.stat().st_size > 0:
            cmd.extend(["--cookies", str(s.COOKIES_PATH)])
        if s.COOKIES_FROM_BROWSER:
            cmd.extend(["--cookies-from-browser", s.COOKIES_FROM_BROWSER])
        if s.PROXY_URL:
            cmd.extend(["--proxy", s.PROXY_URL])
        if s.LIMIT_RATE:
            cmd.extend(["--limit-rate", s.LIMIT_RATE])
        cmd.extend(["--retries", str(s.RETRIES)])

        if s.DATEAFTER:
            cmd.extend(["--dateafter", s.DATEAFTER])
        if s.LIVE_FROM_START:
            cmd.append("--live-from-start")
        if is_playlist:
            cmd.append("--ignore-errors")
        if s.ENABLE_ARCHIVE:
            cmd.extend(["--download-archive", str(s.ARCHIVE_PATH)])
        if s.PLAYLIST_REVERSE:
            cmd.append("--playlist-reverse")
        if s.PLAYLIST_ITEMS:
            cmd.extend(["--playlist-items", s.PLAYLIST_ITEMS])
        if s.CLIP_START and s.CLIP_END:
            cmd.extend(["--download-sections", f"*{s.CLIP_START}-{s.CLIP_END}"])

        # Output template
        if is_playlist:
            # audio playlists go to subfolder of playlist title
            if format_code in ("playlist_mp3", "youtube_music"):
                playlist_template = str(s.DOWNLOADS_DIR / "%(playlist_title)s" / "%(playlist_index)s - %(title)s.%(ext)s")
                cmd.extend(["--yes-playlist", "-o", playlist_template])
            else:
                cmd.extend(["--yes-playlist", "-o", s.PLAYLIST_TEMPLATE])
        else:
            cmd.extend(["-o", s.OUTPUT_TEMPLATE])

        # Organize by uploader
        if s.ORGANIZE_BY_UPLOADER:
            # replace last template argument
            template = cmd[-1]
            if is_playlist:
                template = str(s.DOWNLOADS_DIR / "%(uploader)s" / "%(playlist_index)s - %(title)s.%(ext)s")
            else:
                template = str(s.DOWNLOADS_DIR / "%(uploader)s" / "%(title)s.%(ext)s")
            cmd[-1] = template

        # Formats and post-process
        if is_audio:
            cmd.extend(["-f", "bestaudio", "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0", "--embed-thumbnail"])
            if s.ADD_METADATA:
                cmd.append("--add-metadata")
            if format_code == "youtube_music" and s.YT_MUSIC_METADATA:
                cmd.extend([
                    "--parse-metadata", "description:(?s)(?P<meta_comment>.+)",
                    "--parse-metadata", "%(meta_comment)s:(?P<artist>.+) - .+",
                    "--parse-metadata", "%(meta_comment)s:.+ - (?P<title>.+)",
                ])
            if s.AUDIO_NORMALIZE:
                cmd.append("--audio-normalize")
        else:
            cmd.extend(["-f", format_code, "--merge-output-format", "mkv"])
            if s.ADD_METADATA:
                cmd.append("--add-metadata")

        # SponsorBlock with Shorts-aware throttling
        if s.SPONSORBLOCK_CATEGORIES and not is_short_video(it["url"]):
            cmd.extend(["--sponsorblock-remove", ",".join(s.SPONSORBLOCK_CATEGORIES)])
            cmd.extend(["--sleep-requests", "1", "--sleep-subtitles", "1"])

        # Chapters
        if s.CHAPTERS_MODE == "split":
            cmd.append("--split-chapters")
        elif s.CHAPTERS_MODE == "embed":
            cmd.append("--embed-chapters")

        # Subtitles
        if s.WRITE_SUBS:
            cmd.append("--write-subs")
            if s.SUB_LANGS:
                cmd.extend(["--sub-langs", s.SUB_LANGS])
            if s.WRITE_AUTO_SUBS:
                cmd.append("--write-auto-subs")
            if s.CONVERT_SUBS_TO_SRT:
                cmd.extend(["--convert-subs", "srt"])

        # Custom FFmpeg args (post-processing)
        if s.CUSTOM_FFMPEG_ARGS:
            # Safe cross-platform: rely on yt-dlp postprocessor args instead of shell 'move'
            # This runs after download to produce an additional transformed output
            cmd.extend(["--postprocessor-args", f"ffmpeg:{s.CUSTOM_FFMPEG_ARGS}"])

        cmd.append(it["url"])
        return cmd