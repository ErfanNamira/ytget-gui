# File: ytget/workers/download_worker.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QObject, Signal, QProcess
import os
import re
from pathlib import Path

from ytget.styles import AppStyles
from ytget.settings import AppSettings


@dataclass
class QueueItem:
    url: str
    title: str
    format_code: str


class DownloadWorker(QObject):
    log = Signal(str, str)
    finished = Signal(int)
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
        elif exit_code == 0:
            self.log.emit("✅ Download finished successfully.\n", AppStyles.SUCCESS_COLOR)

            # Post-step: clean "(Music Video)" from audio filenames
            try:
                if self._is_audio_download():
                    cleaned = self._clean_music_video_tags()
                    if cleaned > 0:
                        self.log.emit(f"✨ Cleaned {cleaned} filename(s).\n", AppStyles.SUCCESS_COLOR)
            except Exception as e:
                # Non-fatal: just notify in log
                self.log.emit(f"⚠️ Filename cleanup failed: {e}\n", AppStyles.WARNING_COLOR)

            self.finished.emit(0)
        else:
            self.log.emit(f"❌ yt-dlp exited with code {exit_code}.\n", AppStyles.ERROR_COLOR)
            self.finished.emit(exit_code)

    def _short(self, title: str) -> str:
        return title[:35] + "..." if len(title) > 35 else title

    @staticmethod
    def is_short_video(url: str) -> bool:
        return "youtube.com/shorts/" in url

    def _is_audio_download(self) -> bool:
        format_code = self.item["format_code"]
        return format_code in ("bestaudio", "playlist_mp3", "youtube_music")

    def _build_command(self) -> List[str]:
        s = self.settings
        it = self.item

        cmd: List[str] = [
            str(s.YT_DLP_PATH),
            "--no-warnings",
            "--progress",
            "--output-na-placeholder", "Unknown",
            "--ffmpeg-location", str(s.FFMPEG_PATH.parent),
        ]

        format_code = it["format_code"]
        is_playlist = "list=" in it["url"] or format_code in ("playlist_mp3", "youtube_music")
        is_audio = self._is_audio_download()

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
        fallback_template = "%(artist)s - %(title)s.%(ext)s" if s.YT_MUSIC_METADATA else "%(title)s.%(ext)s"

        if is_playlist:
            template = str(s.DOWNLOADS_DIR / "%(playlist_title)s" / fallback_template)
            cmd.extend(["--yes-playlist", "-o", template])
        else:
            template = str(s.DOWNLOADS_DIR / fallback_template)
            cmd.extend(["-o", template])

        # Audio & post-processing
        if is_audio:
            cmd.extend([
                "-f", "bestaudio",
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "--embed-thumbnail",
            ])
            if s.ADD_METADATA:
                cmd.append("--add-metadata")
            if format_code == "youtube_music" and s.YT_MUSIC_METADATA:
                cmd.extend([
                    "--parse-metadata", "description:(?s)(?P<meta_comment>.+)",
                    "--parse-metadata", "%(meta_comment)s:(?P<artist>[^\\n]+)",
                    "--parse-metadata", "%(meta_comment)s:.+ - (?P<title>[^\\n]+)",
                ])
            if s.AUDIO_NORMALIZE:
                cmd.append("--audio-normalize")
        else:
            cmd.extend(["-f", format_code, "--merge-output-format", "mkv"])
            if s.ADD_METADATA:
                cmd.append("--add-metadata")

        # SponsorBlock handling
        if s.SPONSORBLOCK_CATEGORIES and not self.is_short_video(it["url"]):
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

        # FFmpeg postprocessor args (escaped)
        if s.CUSTOM_FFMPEG_ARGS:
            escaped_args = s.CUSTOM_FFMPEG_ARGS.replace('"', '\\"')
            cmd.extend(["--postprocessor-args", f'ffmpeg:"{escaped_args}"'])

        cmd.append(it["url"])
        return cmd

    def _clean_music_video_tags(self) -> int:
        downloads_root: Path = Path(self.settings.DOWNLOADS_DIR)
        if not downloads_root.exists():
            return 0

        audio_exts = {".mp3"}
        tag_patterns = [
            r"\(music video\)",
            r"\(official video\)",
            r"\(official visualizer\)",
            r"\(video oficial\)",
            r"\[official video\]",
            r"\(drone\)",
            r"\(video\)",
            r"\(visualiser\)",
            r"\(lyric video\)",
            r"\(lyrics\)",
            r"\(audio\)",
            r"\(official track\)",
            r"\(original mix\)",
            r"\(hq\)",
            r"\(hd\)",
            r"\(high quality\)",
            r"\(full song\)",
            r"\(snippet\)",
            r"\(reaction\)",
            r"\(review\)",
            r"\(trailer\)",
            r"\(teaser\)",
            r"\(fan edit\)",
            r"\(studio version\)",
            r"\(youtube\)",
            r"\(vevo\)",
            r"\(tiktok\)",
            r"\(drone shot\)",
            r"\(pov video\)",
        ]
        combined_regex = re.compile(r"\s*(" + "|".join(tag_patterns) + r")", re.IGNORECASE)

        renamed_count = 0
        for root, _dirs, files in os.walk(downloads_root):
            for fname in files:
                p = Path(root) / fname
                if p.suffix.lower() not in audio_exts:
                    continue

                if not combined_regex.search(fname):
                    continue

                new_stem = combined_regex.sub("", p.stem)
                new_stem = re.sub(r"\s{2,}", " ", new_stem).strip(" -_.,")
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
                    renamed_count += 1
                    self.log.emit(f"🧹 Renamed: {p.name} → {new_path.name}\n", AppStyles.INFO_COLOR)
                except Exception as e:
                    self.log.emit(f"⚠️ Could not rename {p.name}: {e}\n", AppStyles.WARNING_COLOR)

        return renamed_count
