# File: ytget_gui/settings.py

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Pattern

from ytget_gui.utils.paths import (
    get_base_path,
    executable_name,
    which_or_path,
    default_downloads_dir,
)


@dataclass
class AppSettings:
    VERSION: str = "2.5.1"
    APP_NAME: str = "YTGet"
    GITHUB_URL: str = "https://github.com/ErfanNamira/ytget-gui"

    BASE_DIR: Path = field(default_factory=get_base_path)
    INTERNAL_DIR: Path = field(init=False)
    DOWNLOADS_DIR: Path = field(default_factory=default_downloads_dir)
    CONFIG_PATH: Path = field(init=False)
    COOKIES_PATH: Path = field(init=False)
    ARCHIVE_PATH: Path = field(init=False)

    YT_DLP_PATH: Path = field(init=False)
    FFMPEG_PATH: Path = field(init=False)
    FFPROBE_PATH: Path = field(init=False)
    PHANTOMJS_PATH: Path = field(init=False)

    OUTPUT_TEMPLATE: str = field(init=False)
    PLAYLIST_TEMPLATE: str = field(init=False)

    YOUTUBE_URL_PATTERN: Pattern = field(
        default_factory=lambda: re.compile(
            r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+",
            re.IGNORECASE,
        )
    )

    RESOLUTIONS: Dict[str, str] = field(
        default_factory=lambda: {
            # --- YouTube-optimized presets (keep existing) ---
            "🎬 YouTube 4320p (8K)": "bestvideo[height=4320][vcodec=vp9]+bestaudio/bestvideo[height<=4320]+bestaudio",
            "🎬 YouTube 2160p (4K)": "251+313/bestvideo[height<=2160]+bestaudio",
            "🎥 YouTube 1440p (QHD)": "251+271/bestvideo[height<=1440]+bestaudio",
            "🎥 YouTube 1080p (FHD)": "251+248/bestvideo[height<=1080]+bestaudio",
            "📱 YouTube 720p (HD)":  "251+247/bestvideo[height<=720]+bestaudio",
            "📱 YouTube 480p (SD)":  "251+244/bestvideo[height<=480]+bestaudio",

            # --- Universal presets (stricter, work across any site supported by yt-dlp) ---
            "🌐 Universal 4320p (8K)": "bestvideo[height<=4320][width<=7680]+bestaudio/best[height<=4320]",
            "🌐 Universal 2160p (4K)": "bestvideo[height<=2160][width<=3840]+bestaudio/best[height<=2160]",
            "🌐 Universal 1440p (QHD)": "bestvideo[height<=1440][width<=2560]+bestaudio/best[height<=1440]",
            "🌐 Universal 1080p (FHD)": "bestvideo[height<=1080][width<=1920]+bestaudio/best[height<=1080]",
            "🌐 Universal 720p (HD)":   "bestvideo[height<=720][width<=1280]+bestaudio/best[height<=720]",
            "🌐 Universal 480p (SD)":   "bestvideo[height<=480][width<=854]+bestaudio/best[height<=480]",

            # --- Audio / playlist presets (unchanged) ---
            "🎵 Single Audio (MP3)": "bestaudio",
            "🎧 Single Audio (FLAC)": "audio_flac",
            "🎶 Audio Playlist (MP3 – YouTube)": "playlist_mp3",
            "🎶 Audio Playlist (MP3 – YouTube Music)": "youtube_music",
        }
    )

    PROXY_URL: str = ""
    SPONSORBLOCK_CATEGORIES: List[str] = field(default_factory=list)
    CHAPTERS_MODE: str = "embed"       # none|embed|split
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
    COOKIES_AUTO_REFRESH: bool = False
    COOKIES_LAST_IMPORTED: str = ""
    LIVE_FROM_START: bool = False
    YT_MUSIC_METADATA: bool = False
    PLAYLIST_ITEMS: str = ""
    CLIP_START: str = ""
    CLIP_END: str = ""
    CUSTOM_FFMPEG_ARGS: str = ""
    CROP_AUDIO_COVERS: bool = True
    VIDEO_FORMAT: str = ".mkv"
    # Thumbnail embedding
    WRITE_THUMBNAIL: bool = False
    CONVERT_THUMBNAILS: bool = True
    THUMBNAIL_FORMAT: str = "png"
    EMBED_THUMBNAIL: bool = True

    def __post_init__(self):
        # Prepare paths
        self.INTERNAL_DIR = (self.BASE_DIR / "_internal").resolve()
        self.CONFIG_PATH = (self.BASE_DIR / "config.json").resolve()
        self.COOKIES_PATH = (self.BASE_DIR / "cookies.txt").resolve()
        self.ARCHIVE_PATH = (self.BASE_DIR / "archive.txt").resolve()

        # Ensure directories exist
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.INTERNAL_DIR.mkdir(parents=True, exist_ok=True)

        # Touch files if missing
        if not self.COOKIES_PATH.exists():
            self.COOKIES_PATH.touch()
        if self.ENABLE_ARCHIVE and not self.ARCHIVE_PATH.exists():
            self.ARCHIVE_PATH.touch()

        # Define bundled candidates
        yt_dlp_candidate = self.BASE_DIR / executable_name("yt-dlp")
        ffmpeg_candidate = self.BASE_DIR / executable_name("ffmpeg")
        ffprobe_candidate = self.BASE_DIR / executable_name("ffprobe")
        phantom_candidate = self.BASE_DIR / executable_name("phantomjs")

        # Resolve via ENV override, then system PATH, then bundled
        yt_env = os.getenv("YTGET_YT_DLP_PATH")
        self.YT_DLP_PATH = Path(yt_env) if yt_env and Path(yt_env).exists() \
            else which_or_path(yt_dlp_candidate, executable_name("yt-dlp"))

        ff_env = os.getenv("YTGET_FFMPEG_PATH")
        self.FFMPEG_PATH = Path(ff_env) if ff_env and Path(ff_env).exists() \
            else which_or_path(ffmpeg_candidate, executable_name("ffmpeg"))

        fp_env = os.getenv("YTGET_FFPROBE_PATH")
        self.FFPROBE_PATH = Path(fp_env) if fp_env and Path(fp_env).exists() \
            else which_or_path(ffprobe_candidate, executable_name("ffprobe"))

        ph_env = os.getenv("YTGET_PHANTOMJS_PATH")
        self.PHANTOMJS_PATH = Path(ph_env) if ph_env and Path(ph_env).exists() \
            else which_or_path(phantom_candidate, executable_name("phantomjs"))
            
        # Output templates
        self.OUTPUT_TEMPLATE = str((self.DOWNLOADS_DIR / "%(title)s.%(ext)s").resolve())
        self.PLAYLIST_TEMPLATE = str((self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s").resolve())

        # Load persisted config last
        self.load_config()

    # -------- Format selection (AV1 -> VP9 map -> best) --------

    def get_format_for_resolution(self, height: int, audio: str = "bestaudio") -> str:
        """
        Build a yt-dlp format string that:
          1) Prefers AV1 at the target height,
          2) Falls back to VP9 mapping,
          3) Falls back to best available at or below that height,
          4) Finally, generic best as a last resort.
        """
        label = self._label_for_height(height)

        av1 = f"bestvideo[height={height}][vcodec=av01]+{audio}"
        vp9_map = self.RESOLUTIONS.get(label, "")
        best_at_or_below = f"bestvideo[height<={height}]+{audio}"
        generic_best = f"bestvideo+{audio}"
        ultimate = "best"

        chain = "/".join([av1, vp9_map, best_at_or_below, generic_best, ultimate])
        return self._dedupe_format_chain(chain)

    def _label_for_height(self, height: int) -> str:
        return {
            4320: "🎬 4320p (8K)",
            2160: "🎬 2160p (4K)",
            1440: "🎬 1440p (QHD)",
            1080: "🎬 1080p (FHD)",
            720:  "🎬 720p (HD)",
            480:  "🎬 480p (SD)",
        }.get(height, f"🎬 {height}p")

    def _dedupe_format_chain(self, chain: str) -> str:
        seen = set()
        parts: List[str] = []
        for seg in (s.strip() for s in chain.split("/") if s.strip()):
            if seg not in seen:
                parts.append(seg)
                seen.add(seg)
        return "/".join(parts)

    # ---------------------- Persistence ----------------------

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
            "COOKIES_AUTO_REFRESH": self.COOKIES_AUTO_REFRESH,
            "COOKIES_LAST_IMPORTED": self.COOKIES_LAST_IMPORTED,
            "LIVE_FROM_START": self.LIVE_FROM_START,
            "YT_MUSIC_METADATA": self.YT_MUSIC_METADATA,
            "PLAYLIST_ITEMS": self.PLAYLIST_ITEMS,
            "CLIP_START": self.CLIP_START,
            "CLIP_END": self.CLIP_END,
            "CUSTOM_FFMPEG_ARGS": self.CUSTOM_FFMPEG_ARGS,
            "CROP_AUDIO_COVERS": self.CROP_AUDIO_COVERS,
            "VIDEO_FORMAT": self.VIDEO_FORMAT,
            "WRITE_THUMBNAIL": self.WRITE_THUMBNAIL,
            "CONVERT_THUMBNAILS": self.CONVERT_THUMBNAILS,
            "THUMBNAIL_FORMAT": self.THUMBNAIL_FORMAT,
            "EMBED_THUMBNAIL": self.EMBED_THUMBNAIL,
            "DOWNLOADS_DIR": str(self.DOWNLOADS_DIR),
            "YT_DLP_PATH": str(self.YT_DLP_PATH),
            "FFMPEG_PATH": str(self.FFMPEG_PATH),
            "FFPROBE_PATH": str(self.FFPROBE_PATH),
            "PHANTOMJS_PATH": str(self.PHANTOMJS_PATH),            
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

            # Basic flags
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
            self.COOKIES_AUTO_REFRESH = config.get("COOKIES_AUTO_REFRESH", self.COOKIES_AUTO_REFRESH)
            self.COOKIES_LAST_IMPORTED = config.get("COOKIES_LAST_IMPORTED", self.COOKIES_LAST_IMPORTED)
            self.LIVE_FROM_START = config.get("LIVE_FROM_START", self.LIVE_FROM_START)
            self.YT_MUSIC_METADATA = config.get("YT_MUSIC_METADATA", self.YT_MUSIC_METADATA)
            self.PLAYLIST_ITEMS = config.get("PLAYLIST_ITEMS", self.PLAYLIST_ITEMS)
            self.CLIP_START = config.get("CLIP_START", self.CLIP_START)
            self.CLIP_END = config.get("CLIP_END", self.CLIP_END)
            self.CUSTOM_FFMPEG_ARGS = config.get("CUSTOM_FFMPEG_ARGS", self.CUSTOM_FFMPEG_ARGS)
            self.CROP_AUDIO_COVERS = config.get("CROP_AUDIO_COVERS", self.CROP_AUDIO_COVERS)
            self.VIDEO_FORMAT = config.get("VIDEO_FORMAT", self.VIDEO_FORMAT)
            # Thumbnail options
            self.WRITE_THUMBNAIL      = config.get("WRITE_THUMBNAIL", self.WRITE_THUMBNAIL)
            self.CONVERT_THUMBNAILS   = config.get("CONVERT_THUMBNAILS", self.CONVERT_THUMBNAILS)
            self.THUMBNAIL_FORMAT     = config.get("THUMBNAIL_FORMAT", self.THUMBNAIL_FORMAT)
            self.EMBED_THUMBNAIL      = config.get("EMBED_THUMBNAIL", self.EMBED_THUMBNAIL)

            # Override download dir if set
            dl_dir = config.get("DOWNLOADS_DIR")
            if dl_dir:
                self.DOWNLOADS_DIR = Path(dl_dir).resolve()
                self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
                self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / "%(title)s.%(ext)s")
                self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s")

            # Override binary paths if valid
            for key, attr in (
                ("YT_DLP_PATH", "YT_DLP_PATH"),
                ("FFMPEG_PATH", "FFMPEG_PATH"),
                ("FFPROBE_PATH", "FFPROBE_PATH"),
                ("PHANTOMJS_PATH", "PHANTOMJS_PATH"),                
                ("COOKIES_PATH", "COOKIES_PATH"),
                ("ARCHIVE_PATH", "ARCHIVE_PATH"),
            ):
                val = config.get(key)
                if val and Path(val).exists():
                    setattr(self, attr, Path(val))

        except Exception as e:
            print(f"Error loading config: {e}")
