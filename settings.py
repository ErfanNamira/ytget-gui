# File: ytget/settings.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Pattern

from ytget.utils.paths import get_base_path, executable_name, which_or_path, default_downloads_dir, is_windows

@dataclass
class AppSettings:
    VERSION: str = "2.4.0"
    APP_NAME: str = "YTGet"
    GITHUB_URL: str = "https://github.com/ErfanNamira/YTGet"

    BASE_DIR: Path = field(default_factory=get_base_path)
    INTERNAL_DIR: Path = field(init=False)
    DOWNLOADS_DIR: Path = field(default_factory=default_downloads_dir)
    CONFIG_PATH: Path = field(init=False)
    COOKIES_PATH: Path = field(init=False)
    ARCHIVE_PATH: Path = field(init=False)

    YT_DLP_PATH: Path = field(init=False)
    FFMPEG_PATH: Path = field(init=False)
    FFPROBE_PATH: Path = field(init=False)

    OUTPUT_TEMPLATE: str = field(init=False)
    PLAYLIST_TEMPLATE: str = field(init=False)

    YOUTUBE_URL_PATTERN: Pattern = field(default_factory=lambda: __import__("re").compile(
        r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+", __import__("re").IGNORECASE
    ))

    RESOLUTIONS: Dict[str, str] = field(default_factory=lambda: {
        "🎬 2160p (4K)": "251+313/bestvideo[height<=2160]+bestaudio",
        "🎬 1440p (QHD)": "251+271/bestvideo[height<=1440]+bestaudio",
        "🎬 1080p (FHD)": "251+248/bestvideo[height<=1080]+bestaudio",
        "🎬 720p (HD)": "251+247/bestvideo[height<=720]+bestaudio",
        "🎬 480p (SD)": "251+244/bestvideo[height<=480]+bestaudio",
        "🎵 Single Audio (MP3)": "bestaudio",
        "🎵 Audio Playlist (MP3 – YouTube)": "playlist_mp3",
        "🎵 Audio Playlist (MP3 – YouTube Music)": "youtube_music",
    })

    PROXY_URL: str = ""
    SPONSORBLOCK_CATEGORIES: List[str] = field(default_factory=list)
    CHAPTERS_MODE: str = "embed"  # none|embed|split
    WRITE_SUBS: bool = False
    SUB_LANGS: str = "en"
    WRITE_AUTO_SUBS: bool = False
    CONVERT_SUBS_TO_SRT: bool = False
    ENABLE_ARCHIVE: bool = False
    PLAYLIST_REVERSE: bool = False
    AUDIO_NORMALIZE: bool = False
    ADD_METADATA: bool = True
    LIMIT_RATE: str = ""
    RETRIES: int = 10
    ORGANIZE_BY_UPLOADER: bool = False
    DATEAFTER: str = ""
    COOKIES_FROM_BROWSER: str = ""
    LIVE_FROM_START: bool = False
    YT_MUSIC_METADATA: bool = False
    PLAYLIST_ITEMS: str = ""
    CLIP_START: str = ""
    CLIP_END: str = ""
    CUSTOM_FFMPEG_ARGS: str = ""
    CROP_AUDIO_COVERS: bool = True

    def __post_init__(self):
        self.INTERNAL_DIR = (self.BASE_DIR / "_internal").resolve()
        self.CONFIG_PATH = (self.BASE_DIR / "config.json").resolve()
        self.COOKIES_PATH = (self.BASE_DIR / "cookies.txt").resolve()
        self.ARCHIVE_PATH = (self.BASE_DIR / "archive.txt").resolve()

        # Resolve binaries with PATH fallback
        yt_dlp_candidate = self.BASE_DIR / executable_name("yt-dlp")
        ffmpeg_candidate = self.BASE_DIR / executable_name("ffmpeg")
        ffprobe_candidate = self.BASE_DIR / executable_name("ffprobe")

        self.YT_DLP_PATH = which_or_path(yt_dlp_candidate, executable_name("yt-dlp"))
        self.FFMPEG_PATH = which_or_path(ffmpeg_candidate, executable_name("ffmpeg"))
        self.FFPROBE_PATH = which_or_path(ffprobe_candidate, executable_name("ffprobe"))

        self.OUTPUT_TEMPLATE = str((self.DOWNLOADS_DIR / "%(title)s.%(ext)s").resolve())
        self.PLAYLIST_TEMPLATE = str((self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s").resolve())

        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.INTERNAL_DIR.mkdir(parents=True, exist_ok=True)

        if not self.COOKIES_PATH.exists():
            self.COOKIES_PATH.touch()

        if self.ENABLE_ARCHIVE and not self.ARCHIVE_PATH.exists():
            self.ARCHIVE_PATH.touch()

        # Load config last to override any defaults
        self.load_config()

    # Persistence
    def set_download_path(self, path: Path):
        self.DOWNLOADS_DIR = path.resolve()
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / "%(title)s.%(ext)s")
        self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s")
        self.save_config()

    def save_config(self):
        config = {
            "PROXY_URL": self.PROXY_URL,
            "SPONSORBLOCK_CATEGORIES": self.SPONSORBLOCK_CATEGORIES,
            "CHAPTERS_MODE": self.CHAPTERS_MODE,
            "WRITE_SUBS": self.WRITE_SUBS,
            "SUB_LANGS": self.SUB_LANGS,
            "WRITE_AUTO_SUBS": self.WRITE_AUTO_SUBS,
            "CONVERT_SUBS_TO_SRT": self.CONVERT_SUBS_TO_SRT,
            "ENABLE_ARCHIVE": self.ENABLE_ARCHIVE,
            "PLAYLIST_REVERSE": self.PLAYLIST_REVERSE,
            "AUDIO_NORMALIZE": self.AUDIO_NORMALIZE,
            "ADD_METADATA": self.ADD_METADATA,
            "LIMIT_RATE": self.LIMIT_RATE,
            "RETRIES": self.RETRIES,
            "ORGANIZE_BY_UPLOADER": self.ORGANIZE_BY_UPLOADER,
            "DATEAFTER": self.DATEAFTER,
            "COOKIES_FROM_BROWSER": self.COOKIES_FROM_BROWSER,
            "LIVE_FROM_START": self.LIVE_FROM_START,
            "YT_MUSIC_METADATA": self.YT_MUSIC_METADATA,
            "PLAYLIST_ITEMS": self.PLAYLIST_ITEMS,
            "CLIP_START": self.CLIP_START,
            "CLIP_END": self.CLIP_END,
            "CUSTOM_FFMPEG_ARGS": self.CUSTOM_FFMPEG_ARGS,
            "CROP_AUDIO_COVERS": self.CROP_AUDIO_COVERS,
            "DOWNLOADS_DIR": str(self.DOWNLOADS_DIR),
            "YT_DLP_PATH": str(self.YT_DLP_PATH),
            "FFMPEG_PATH": str(self.FFMPEG_PATH),
            "FFPROBE_PATH": str(self.FFPROBE_PATH),
            "COOKIES_PATH": str(self.COOKIES_PATH),
            "ARCHIVE_PATH": str(self.ARCHIVE_PATH),
        }
        with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def load_config(self):
        if not self.CONFIG_PATH.exists():
            return
        try:
            config = json.loads(self.CONFIG_PATH.read_text(encoding="utf-8"))
            self.PROXY_URL = config.get("PROXY_URL", self.PROXY_URL)
            self.SPONSORBLOCK_CATEGORIES = config.get("SPONSORBLOCK_CATEGORIES", self.SPONSORBLOCK_CATEGORIES)
            self.CHAPTERS_MODE = config.get("CHAPTERS_MODE", self.CHAPTERS_MODE)
            self.WRITE_SUBS = config.get("WRITE_SUBS", self.WRITE_SUBS)
            self.SUB_LANGS = config.get("SUB_LANGS", self.SUB_LANGS)
            self.WRITE_AUTO_SUBS = config.get("WRITE_AUTO_SUBS", self.WRITE_AUTO_SUBS)
            self.CONVERT_SUBS_TO_SRT = config.get("CONVERT_SUBS_TO_SRT", self.CONVERT_SUBS_TO_SRT)
            self.ENABLE_ARCHIVE = config.get("ENABLE_ARCHIVE", self.ENABLE_ARCHIVE)
            self.PLAYLIST_REVERSE = config.get("PLAYLIST_REVERSE", self.PLAYLIST_REVERSE)
            self.AUDIO_NORMALIZE = config.get("AUDIO_NORMALIZE", self.AUDIO_NORMALIZE)
            self.ADD_METADATA = config.get("ADD_METADATA", self.ADD_METADATA)
            self.LIMIT_RATE = config.get("LIMIT_RATE", self.LIMIT_RATE)
            self.RETRIES = config.get("RETRIES", self.RETRIES)
            self.ORGANIZE_BY_UPLOADER = config.get("ORGANIZE_BY_UPLOADER", self.ORGANIZE_BY_UPLOADER)
            self.DATEAFTER = config.get("DATEAFTER", self.DATEAFTER)
            self.COOKIES_FROM_BROWSER = config.get("COOKIES_FROM_BROWSER", self.COOKIES_FROM_BROWSER)
            self.LIVE_FROM_START = config.get("LIVE_FROM_START", self.LIVE_FROM_START)
            self.YT_MUSIC_METADATA = config.get("YT_MUSIC_METADATA", self.YT_MUSIC_METADATA)
            self.PLAYLIST_ITEMS = config.get("PLAYLIST_ITEMS", self.PLAYLIST_ITEMS)
            self.CLIP_START = config.get("CLIP_START", self.CLIP_START)
            self.CLIP_END = config.get("CLIP_END", self.CLIP_END)
            self.CUSTOM_FFMPEG_ARGS = config.get("CUSTOM_FFMPEG_ARGS", self.CUSTOM_FFMPEG_ARGS)
            self.CROP_AUDIO_COVERS = config.get("CROP_AUDIO_COVERS", self.CROP_AUDIO_COVERS)

            # Paths (allow user to override)
            dl_dir = config.get("DOWNLOADS_DIR")
            if dl_dir:
                self.DOWNLOADS_DIR = Path(dl_dir).resolve()
                self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
                self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / "%(title)s.%(ext)s")
                self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s")

            y = config.get("YT_DLP_PATH")
            f = config.get("FFMPEG_PATH")
            p = config.get("FFPROBE_PATH")
            c = config.get("COOKIES_PATH")
            a = config.get("ARCHIVE_PATH")
            if y: self.YT_DLP_PATH = Path(y)
            if f: self.FFMPEG_PATH = Path(f)
            if p: self.FFPROBE_PATH = Path(p)
            if c: self.COOKIES_PATH = Path(c)
            if a: self.ARCHIVE_PATH = Path(a)

        except Exception as e:

            print(f"Error loading config: {e}")
